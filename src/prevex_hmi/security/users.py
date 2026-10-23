from __future__ import annotations
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import time

ROLES={"Viewer":0,"Operator":1,"Administrator":2}


class UserStore:
    def __init__(self,path: Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, salt BLOB NOT NULL, digest BLOB NOT NULL, role TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, name TEXT NOT NULL, expires REAL NOT NULL);
        """)

    def has_users(self):
        return bool(self.db.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def create_user(self,name,password,role="Administrator",*,session=""):
        if self.has_users() and self.resolve(session)[1] != "Administrator":
            raise PermissionError("Administrator required")
        if not name.strip() or len(password) < 12 or role not in ROLES:
            raise ValueError("Username and a password of at least12 characters required")
        if not self.has_users() and role != "Administrator":
            raise PermissionError("First account must be Administrator")
        salt=secrets.token_bytes(32)
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600_000)
        self.db.execute("INSERT INTO users VALUES (?,?,?,?)",(name.strip(),salt,digest,role))
        self.db.commit()

    def authenticate(self,name,password):
        row=self.db.execute("SELECT salt,digest FROM users WHERE name=?",(name,)).fetchone()
        salt,digest=row if row else (b"\x00"*32,b"\x00"*32)
        candidate=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600_000)
        if not hmac.compare_digest(candidate,digest):
            raise PermissionError("Invalid username or password")
        token=secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM sessions WHERE expires < ?",(time.time(),))
        self.db.execute("INSERT INTO sessions VALUES (?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),name,time.time()+8*3600))
        self.db.commit()
        return token

    def resolve(self,token):
        row=self.db.execute("SELECT u.name,u.role FROM sessions s JOIN users u ON u.name=s.name WHERE s.token_hash=? AND s.expires>?",(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return tuple(row) if row else ("Guest","Viewer")

    def logout(self,token):
        self.db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
        self.db.commit()

    def close(self):
        self.db.close()
