from __future__ import annotations
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime,timezone

ROLES={"Viewer":0,"Operator":1,"Administrator":2}


class UserStore:
    def __init__(self,path: Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=5)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, salt BLOB NOT NULL, digest BLOB NOT NULL, role TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, name TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS account_audit (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL);
        """)
        with self._write():
            columns={row[1] for row in self.db.execute('PRAGMA table_info(users)')}
            for name in ('active','must_change'):
                if name not in columns:self.db.execute(f'ALTER TABLE users ADD COLUMN {name} INTEGER NOT NULL DEFAULT {1 if name=="active" else 0}')

    @contextmanager
    def _write(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield
        except Exception:self.db.rollback();raise
        else:self.db.commit()

    @staticmethod
    def _password(password):
        if not isinstance(password,str) or not 12<=len(password)<=1024 or not password.strip():
            raise ValueError('Password must contain12–1024 characters')
        salt=secrets.token_bytes(32)
        return salt,hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600_000)

    def session_info(self,token):
        row=self.db.execute('SELECT u.name,u.role,u.must_change FROM sessions s JOIN users u ON u.name=s.name WHERE s.token_hash=? AND s.expires>? AND u.active=1',
                            (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return None if row is None else dict(name=row[0],role=row[1],must_change=bool(row[2]))

    def _actor(self,token,*,admin=False):
        info=self.session_info(token)
        if not info:raise PermissionError('Please sign in again')
        if admin and (info['role']!='Administrator' or info['must_change']):raise PermissionError('Administrator required; complete any required password change first')
        return info['name']

    def _audit(self,actor,action,target,detail):
        self.db.execute('INSERT INTO account_audit(timestamp,actor,action,target,detail) VALUES (?,?,?,?,?)',
                        (datetime.now(timezone.utc).isoformat(timespec='milliseconds'),actor,action,target,detail))

    def _target(self,name):
        row=self.db.execute('SELECT role FROM users WHERE name=? AND active=1',(name,)).fetchone()
        if row is None:raise ValueError('User no longer exists')
        return row[0]

    def _protect_last_admin(self,name,new_role=None):
        if self._target(name)=='Administrator' and new_role!='Administrator' and self.db.execute("SELECT COUNT(*) FROM users WHERE active=1 AND role='Administrator'").fetchone()[0]<=1:
            raise PermissionError('The last Administrator account must remain active')

    def has_users(self):
        return bool(self.db.execute("SELECT 1 FROM users WHERE active=1 LIMIT 1").fetchone())

    def create_user(self,name,password,role="Administrator",*,session="",require_change=False):
        if self.has_users() and self.resolve(session)[1] != "Administrator":
            raise PermissionError("Administrator required")
        name=name.strip()
        if not 1<=len(name)<=64 or any(ord(c)<32 or ord(c)==127 for c in name) or role not in ROLES:
            raise ValueError('Choose a username of1–64 printable characters and a valid role')
        salt,digest=self._password(password)
        try:
            with self._write():
                first=not self.has_users()
                actor='Initial setup' if first else self._actor(session,admin=True)
                if first and role!='Administrator':raise PermissionError('First account must be Administrator')
                self.db.execute('INSERT INTO users(name,salt,digest,role,active,must_change) VALUES (?,?,?,?,1,?)',(name,salt,digest,role,int(bool(require_change and not first))))
                self._audit(actor,'CREATE',name,f'Role: {role}; password change required: {bool(require_change and not first)}')
        except sqlite3.IntegrityError as error:raise ValueError('Username already exists or is reserved by an archived account') from error

    def authenticate(self,name,password):
        row=self.db.execute("SELECT salt,digest FROM users WHERE name=? AND active=1",(name,)).fetchone()
        salt,digest=row if row else (b"\x00"*32,b"\x00"*32)
        candidate=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600_000)
        matches=hmac.compare_digest(candidate,digest)
        if row is None or not matches:
            raise PermissionError("Invalid username or password")
        token=secrets.token_urlsafe(32)
        with self._write():
            current=self.db.execute('SELECT salt,digest FROM users WHERE name=? AND active=1',(name,)).fetchone()
            if current is None or current!=row:raise PermissionError('Account changed; sign in again')
            self.db.execute("DELETE FROM sessions WHERE expires < ?",(time.time(),))
            self.db.execute("INSERT INTO sessions VALUES (?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),name,time.time()+8*3600))
        return token

    def resolve(self,token):
        info=self.session_info(token)
        return (info['name'],'Viewer' if info['must_change'] else info['role']) if info else ('Guest','Viewer')

    def list_users(self,session):
        self._actor(session,admin=True)
        return self.db.execute('SELECT name,role,must_change FROM users WHERE active=1 ORDER BY name COLLATE NOCASE').fetchall()

    def change_password(self,session,current_password,new_password):
        actor=self._actor(session)
        row=self.db.execute('SELECT salt,digest FROM users WHERE name=? AND active=1',(actor,)).fetchone()
        if row is None:raise PermissionError('Account changed; sign in again')
        if not hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',current_password.encode(),row[0],600_000),row[1]):raise PermissionError('Current password is incorrect')
        if current_password==new_password:raise ValueError('Choose a different password')
        salt,digest=self._password(new_password)
        with self._write():
            self._actor(session)
            # Recheck the verified digest: another administrator may have reset it.
            if self.db.execute('SELECT digest FROM users WHERE name=?',(actor,)).fetchone()[0]!=row[1]:raise PermissionError('Account changed; sign in again')
            self.db.execute('UPDATE users SET salt=?,digest=?,must_change=0 WHERE name=?',(salt,digest,actor))
            self.db.execute('DELETE FROM sessions WHERE name=?',(actor,))
            self._audit(actor,'CHANGE_PASSWORD',actor,'All sessions revoked')

    def reset_password(self,session,name,new_password):
        actor=self._actor(session,admin=True)
        if name==actor:raise PermissionError('Use Change my password for your own account')
        salt,digest=self._password(new_password)
        with self._write():
            actor=self._actor(session,admin=True);self._target(name)
            self.db.execute('UPDATE users SET salt=?,digest=?,must_change=1 WHERE name=?',(salt,digest,name))
            self.db.execute('DELETE FROM sessions WHERE name=?',(name,))
            self._audit(actor,'RESET_PASSWORD',name,'Password change required on next sign-in; all sessions revoked')

    def change_role(self,session,name,role):
        if role not in ROLES:raise ValueError('Invalid role')
        with self._write():
            actor=self._actor(session,admin=True);previous=self._target(name)
            if previous==role:return
            self._protect_last_admin(name,role)
            self.db.execute('UPDATE users SET role=? WHERE name=?',(role,name))
            self.db.execute('DELETE FROM sessions WHERE name=?',(name,))
            self._audit(actor,'CHANGE_ROLE',name,f'{previous} -> {role}; all sessions revoked')

    def delete_user(self,session,name):
        with self._write():
            actor=self._actor(session,admin=True)
            if name==actor:raise PermissionError('You cannot delete your own signed-in account')
            self._protect_last_admin(name)
            self.db.execute('UPDATE users SET active=0 WHERE name=?',(name,))
            self.db.execute('DELETE FROM sessions WHERE name=?',(name,))
            self._audit(actor,'DELETE',name,'Account archived; sessions revoked; audit history retained')

    def account_history(self,session):
        self._actor(session,admin=True)
        return self.db.execute('SELECT timestamp,actor,action,target,detail FROM account_audit ORDER BY id DESC LIMIT 200').fetchall()

    def logout(self,token):
        self.db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
        self.db.commit()

    def close(self):
        self.db.close()
