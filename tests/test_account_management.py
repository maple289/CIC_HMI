"""Local account lifecycle and UI tests use isolated temporary databases only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,os,sqlite3,threading
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QDialog,QLineEdit,QMessageBox
from prevex_hmi.security.users import UserStore
from prevex_hmi.gui.accounts import AccountsDialog,AccountPasswordDialog
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.gui.profile_library import library_config
from dataclasses import asdict

ADMIN='administrator-test-password'
OPERATOR='operator-test-password'
NEW='replacement-test-password'


def test_eight_character_password_boundary_for_creation_change_and_reset(tmp_path):
    users=UserStore(tmp_path/'password-boundary.sqlite3')
    try:
        with pytest.raises(ValueError):users.create_user('admin','short77')
        users.create_user('admin','admin888');admin=users.authenticate('admin','admin888')
        with pytest.raises(ValueError):users.create_user('viewer','short77','Viewer',session=admin)
        users.create_user('viewer','viewer88','Viewer',session=admin)
        viewer=users.authenticate('viewer','viewer88')
        with pytest.raises(ValueError):users.change_password(viewer,'viewer88','short77')
        users.change_password(viewer,'viewer88','changed8')
        assert users.resolve(users.authenticate('viewer','changed8'))==('viewer','Viewer')
        with pytest.raises(ValueError):users.reset_password(admin,'viewer','short77')
        users.reset_password(admin,'viewer','reset888')
        assert users.session_info(users.authenticate('viewer','reset888'))['must_change']
    finally:users.close()


@pytest.fixture
def store(tmp_path):
    users=UserStore(tmp_path/'accounts.sqlite3');users.create_user('admin',ADMIN)
    token=users.authenticate('admin',ADMIN)
    users.create_user('operator',OPERATOR,'Operator',session=token)
    other=users.authenticate('operator',OPERATOR)
    yield users,token,other,tmp_path/'accounts.sqlite3'
    users.close()


@pytest.fixture
def app(monkeypatch):
    result=QApplication.instance() or QApplication([]);result.setQuitOnLastWindowClosed(False)
    monkeypatch.setattr(QMessageBox,'warning',lambda *a,**k:QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox,'information',lambda *a,**k:QMessageBox.Ok)
    return result


def test_password_change_requires_current_password_and_revokes_all_sessions(store):
    users,admin,operator,_=store;second=users.authenticate('operator',OPERATOR)
    previous=users.db.execute("SELECT salt,digest FROM users WHERE name='operator'").fetchone()
    with pytest.raises(PermissionError):users.change_password(operator,'wrong-current-password',NEW)
    assert users.resolve(operator)==('operator','Operator')
    for bad in ('short',' '*15,OPERATOR):
        with pytest.raises(ValueError):users.change_password(operator,OPERATOR,bad)
    users.change_password(operator,OPERATOR,NEW)
    assert users.resolve(operator)==users.resolve(second)==('Guest','Viewer')
    with pytest.raises(PermissionError):users.authenticate('operator',OPERATOR)
    assert users.resolve(users.authenticate('operator',NEW))==('operator','Operator')
    current=users.db.execute("SELECT salt,digest FROM users WHERE name='operator'").fetchone()
    assert current!=previous and len(current[0])==len(current[1])==32
    history=users.account_history(admin)
    assert history[0][2:4]==('CHANGE_PASSWORD','operator')
    assert ADMIN not in str(history) and OPERATOR not in str(history) and NEW not in str(history)


@pytest.mark.parametrize('action',['create','reset','role','delete','list','audit'])
def test_operator_and_forged_sessions_cannot_manage_users(store,action):
    users,_,operator,_=store
    for token in (operator,'forged-token'):
        with pytest.raises(PermissionError):
            if action=='create':users.create_user('intruder',NEW,'Administrator',session=token)
            elif action=='reset':users.reset_password(token,'admin',NEW)
            elif action=='role':users.change_role(token,'operator','Administrator')
            elif action=='delete':users.delete_user(token,'admin')
            elif action=='list':users.list_users(token)
            else:users.account_history(token)
    assert users.resolve(operator)==('operator','Operator')


def test_reset_requires_rotation_and_does_not_grant_privileges(store):
    users,admin,operator,_=store
    users.reset_password(admin,'operator',NEW)
    assert users.resolve(operator)==('Guest','Viewer')
    temporary=users.authenticate('operator',NEW)
    assert users.session_info(temporary)['must_change']
    assert users.resolve(temporary)==('operator','Viewer')
    users.change_password(temporary,NEW,'personal-replacement-password')
    fresh=users.authenticate('operator','personal-replacement-password')
    assert users.resolve(fresh)==('operator','Operator') and not users.session_info(fresh)['must_change']
    with pytest.raises(PermissionError):users.reset_password(admin,'admin',NEW)


def test_admin_reset_and_create_force_password_change_before_admin_management(store):
    users,admin,_,_=store
    users.create_user('second-admin',NEW,'Administrator',session=admin,require_change=True)
    temporary=users.authenticate('second-admin',NEW)
    assert users.resolve(temporary)==('second-admin','Viewer')
    with pytest.raises(PermissionError):users.list_users(temporary)
    users.change_password(temporary,NEW,'second-admin-personal-password')
    second=users.authenticate('second-admin','second-admin-personal-password')
    assert users.resolve(second)==('second-admin','Administrator')


def test_last_admin_self_delete_and_session_revocation(store):
    users,admin,operator,_=store
    with pytest.raises(PermissionError):users.change_role(admin,'admin','Viewer')
    with pytest.raises(PermissionError):users.delete_user(admin,'admin')
    users.change_role(admin,'operator','Viewer')
    assert users.resolve(operator)==('Guest','Viewer')
    assert users.resolve(users.authenticate('operator',OPERATOR))==('operator','Viewer')
    users.create_user('second-admin',NEW,'Administrator',session=admin)
    second=users.authenticate('second-admin',NEW)
    users.change_role(admin,'admin','Operator')
    assert users.resolve(admin)==('Guest','Viewer')
    with pytest.raises(PermissionError):users.change_role(second,'second-admin','Viewer')


def test_deletion_archives_identity_and_keeps_audit(store):
    users,admin,operator,_=store;users.delete_user(admin,'operator')
    assert users.resolve(operator)==('Guest','Viewer')
    with pytest.raises(PermissionError):users.authenticate('operator',OPERATOR)
    assert [r[0] for r in users.list_users(admin)]==['admin']
    assert users.account_history(admin)[0][2]=='DELETE'
    with pytest.raises(ValueError):users.create_user('operator',NEW,'Viewer',session=admin)
    users.create_user('new-user',NEW,'Viewer',session=admin)
    assert users.resolve(users.authenticate('new-user',NEW))==('new-user','Viewer')


def test_audit_failure_rolls_back_role_change_and_session_deletion(store,monkeypatch):
    users,admin,operator,_=store
    def failure(*args):raise RuntimeError('Audit storage unavailable')
    monkeypatch.setattr(users,'_audit',failure)
    with pytest.raises(RuntimeError):users.change_role(admin,'operator','Viewer')
    assert users.resolve(operator)==('operator','Operator')


def test_two_admin_changes_cannot_remove_the_last_admin(store):
    users,admin,_,path=store
    users.create_user('second-admin',NEW,'Administrator',session=admin)
    second=users.authenticate('second-admin',NEW);barrier=threading.Barrier(2)
    def demote(name,token):
        instance=UserStore(path)
        try:
            barrier.wait(timeout=5)
            try:instance.change_role(token,name,'Viewer');return True
            except PermissionError:return False
        finally:instance.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(demote,'admin',admin),pool.submit(demote,'second-admin',second)]
        results=[f.result(timeout=10) for f in futures]
    assert sum(results)==1
    assert users.db.execute("SELECT COUNT(*) FROM users WHERE active=1 AND role='Administrator'").fetchone()[0]==1


def test_password_reset_during_login_cannot_issue_a_session_for_old_credentials(store,monkeypatch):
    users,admin,_,path=store;other=UserStore(path);original=hashlib.pbkdf2_hmac;triggered=[False]
    def interleaved(algorithm,password,salt,iterations):
        if password==OPERATOR.encode() and not triggered[0]:
            triggered[0]=True;other.reset_password(admin,'operator',NEW)
        return original(algorithm,password,salt,iterations)
    monkeypatch.setattr(hashlib,'pbkdf2_hmac',interleaved)
    try:
        with pytest.raises(PermissionError):users.authenticate('operator',OPERATOR)
        assert users.session_info(users.authenticate('operator',NEW))['must_change']
    finally:other.close()


def test_existing_database_migrates_without_changing_password_or_role(tmp_path):
    path=tmp_path/'legacy.sqlite3';db=sqlite3.connect(path)
    db.executescript('CREATE TABLE users(name TEXT PRIMARY KEY,salt BLOB NOT NULL,digest BLOB NOT NULL,role TEXT NOT NULL); CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,name TEXT NOT NULL,expires REAL NOT NULL);')
    salt=b'x'*32;digest=hashlib.pbkdf2_hmac('sha256',ADMIN.encode(),salt,600_000)
    db.execute('INSERT INTO users VALUES (?,?,?,?)',('legacy-admin',salt,digest,'Administrator'));db.commit();db.close()
    users=UserStore(path)
    try:
        token=users.authenticate('legacy-admin',ADMIN)
        assert users.resolve(token)==('legacy-admin','Administrator')
        assert not users.session_info(token)['must_change']
        assert users.db.execute('SELECT salt,digest FROM users').fetchone()==(salt,digest)
    finally:users.close()


def test_account_ui_permissions_create_and_password_change(app,store):
    users,admin,operator,_=store
    viewer=AccountsDialog(users,operator);manager=AccountsDialog(users,admin)
    try:
        assert viewer.tabs.count()==1 and manager.tabs.count()==3
        assert viewer.current.echoMode()==QLineEdit.Password
        create=AccountPasswordDialog(users,admin)
        assert create.role.currentText()=='Viewer' and create.require_change.isChecked()
        create.name.setText('new-viewer');create.password.setText(NEW);create.confirm.setText(NEW);create.accept()
        assert create.result()==QDialog.Accepted and not create.password.text() and not create.confirm.text()
        assert users.session_info(users.authenticate('new-viewer',NEW))['must_change']
        viewer.current.setText(OPERATOR);viewer.password.setText(NEW);viewer.confirm.setText(NEW);viewer.change_password()
        assert viewer.result()==QDialog.Accepted and not viewer.current.text() and not viewer.password.text()
        assert users.resolve(users.authenticate('operator',NEW))==('operator','Operator')
    finally:viewer.close();manager.close();app.processEvents()


def test_delete_confirmation_and_last_admin_error_leave_access_intact(app,store,monkeypatch):
    users,admin,operator,_=store;dialog=AccountsDialog(users,admin)
    try:
        row=next(i for i in range(dialog.users_table.rowCount()) if dialog.users_table.item(i,0).text()=='operator')
        dialog.users_table.selectRow(row);monkeypatch.setattr(dialog,'confirm_action',lambda *a:False)
        dialog.delete_user();assert users.resolve(operator)==('operator','Operator')
        monkeypatch.setattr(dialog,'confirm_action',lambda *a:True);dialog.delete_user()
        assert users.resolve(operator)==('Guest','Viewer')
        dialog.users_table.selectRow(0);dialog.role.setCurrentText('Viewer');dialog.change_role()
        assert users.resolve(admin)==('admin','Administrator')
    finally:dialog.close();app.processEvents()


def test_revoked_session_disables_existing_operating_controls(app,tmp_path):
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path,start_worker=False)
    users=w.users;users.create_user('admin',ADMIN);admin=users.authenticate('admin',ADMIN)
    users.create_user('operator',OPERATOR,'Operator',session=admin);w.session=users.authenticate('operator',OPERATOR)
    config=library_config('LEL 670 Series')
    w.snapshot=dict(config=asdict(config),raw={2:0,60:0},quality='GOOD',control=dict(verified=True))
    w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False)
    try:
        w.update_command_buttons();assert w.command_buttons[0x300].isEnabled() and w.account_button.isEnabled()
        users.reset_password(admin,'operator',NEW);w.update_command_buttons()
        assert not w.session and not w.account_button.isEnabled()
        assert not any(b.isEnabled() for b in w.command_buttons.values())
    finally:w.worker=None;w.close();app.processEvents()
