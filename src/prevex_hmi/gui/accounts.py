"""Local account/password workflows; authorization is enforced by UserStore."""
import sqlite3
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView,QCheckBox,QComboBox,QDialog,QDialogButtonBox,
    QFormLayout,QHBoxLayout,QHeaderView,QLabel,QLineEdit,QMessageBox,QPushButton,
    QTableWidget,QTableWidgetItem,QTabWidget,QVBoxLayout,QWidget)
from prevex_hmi.security.users import ROLES


def password_field():
    field=QLineEdit();field.setEchoMode(QLineEdit.Password);field.setMaxLength(1024)
    return field


def fill_table(table,rows):
    blocked=table.blockSignals(True)
    try:
        table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):table.setItem(i,j,QTableWidgetItem(str(value)))
    finally:table.blockSignals(blocked)


def account_table(headers):
    table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True);table.verticalHeader().hide()
    return table


class AccountPasswordDialog(QDialog):
    def __init__(self,users,session,parent=None,*,target=None):
        super().__init__(parent);self.users,self.session,self.target=users,session,target
        self.setWindowTitle('Reset user password' if target else 'Create user');self.setMinimumWidth(440)
        form=QFormLayout(self)
        self.name=QLineEdit(target or '');self.name.setMaxLength(32767 if target else 64);self.name.setReadOnly(target is not None)
        self.role=QComboBox();self.role.addItems(ROLES);self.role.setCurrentText('Viewer')
        self.password=password_field();self.confirm=password_field()
        form.addRow('Username',self.name)
        if not target:form.addRow('Role',self.role)
        form.addRow('New password (8–1024 characters)',self.password);form.addRow('Confirm new password',self.confirm)
        self.require_change=QCheckBox('Require password change at next sign-in');self.require_change.setChecked(True)
        if not target:form.addRow(self.require_change)
        note=QLabel('Resetting a password signs out the user’s existing sessions and requires a new password at their next sign-in.' if target else 'Give the initial password to the user through your normal secure process. The HMI never displays stored passwords.')
        note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)
        self.finished.connect(lambda _:self.clear_passwords())

    def clear_passwords(self):self.password.clear();self.confirm.clear()

    def accept(self):
        try:
            if self.password.text()!=self.confirm.text():raise ValueError('Passwords do not match')
            if self.target:self.users.reset_password(self.session,self.target,self.password.text())
            else:self.users.create_user(self.name.text(),self.password.text(),self.role.currentText(),session=self.session,require_change=self.require_change.isChecked())
        except (ValueError,PermissionError,sqlite3.Error) as error:
            QMessageBox.warning(self,'Account update failed',str(error));return
        self.clear_passwords();super().accept()


class AccountsDialog(QDialog):
    def __init__(self,users,session,parent=None):
        super().__init__(parent);self.users,self.session=users,session
        info=users.session_info(session)
        if not info:raise PermissionError('Please sign in first')
        self.name=info['name'];self.is_admin=info['role']=='Administrator' and not info['must_change']
        self.setWindowTitle('My account / User management');self.resize(820,590)
        root=QVBoxLayout(self);self.tabs=QTabWidget();root.addWidget(self.tabs)
        own=QWidget();form=QFormLayout(own)
        note=QLabel(f"Signed in as {info['name']} / {info['role']}. "+('Password change required before operating controls are available.' if info['must_change'] else 'Changing your password signs out all your sessions.'))
        note.setTextFormat(Qt.PlainText);note.setWordWrap(True);form.addRow(note)
        self.current=password_field();self.current.setMaxLength(32767)
        self.password=password_field();self.confirm=password_field()
        form.addRow('Current password',self.current);form.addRow('New password (8–1024 characters)',self.password);form.addRow('Confirm new password',self.confirm)
        change=QPushButton('Change my password');change.clicked.connect(self.change_password);form.addRow(change)
        self.tabs.addTab(own,'My password')
        if self.is_admin:
            manage=QWidget();body=QVBoxLayout(manage)
            label=QLabel('Keep at least one Administrator. Removing a user archives the account and preserves the audit history. Role/password changes sign out that user’s sessions.')
            label.setWordWrap(True);body.addWidget(label)
            self.users_table=account_table(['Username','Role','Password change required']);body.addWidget(self.users_table)
            row=QHBoxLayout();create=QPushButton('Create user...');create.clicked.connect(self.create_user);row.addWidget(create)
            self.reset_button=QPushButton('Reset password...');self.reset_button.clicked.connect(self.reset_password);row.addWidget(self.reset_button)
            self.delete_button=QPushButton('Delete user...');self.delete_button.clicked.connect(self.delete_user);row.addWidget(self.delete_button);body.addLayout(row)
            row=QHBoxLayout();row.addWidget(QLabel('Selected user’s role'));self.role=QComboBox();self.role.addItems(ROLES);row.addWidget(self.role)
            self.role_button=QPushButton('Apply role change');self.role_button.clicked.connect(self.change_role);row.addWidget(self.role_button);body.addLayout(row)
            self.tabs.addTab(manage,'Users')
            audit=QWidget();audit_layout=QVBoxLayout(audit);self.audit_table=account_table(['UTC timestamp','Administrator / user','Action','Target','Detail']);audit_layout.addWidget(self.audit_table)
            refresh=QPushButton('Refresh account audit');refresh.clicked.connect(self.refresh);audit_layout.addWidget(refresh);self.tabs.addTab(audit,'Account audit')
            self.users_table.itemSelectionChanged.connect(self.selection_changed);self.refresh()
        close=QPushButton('Cancel and sign out' if info['must_change'] else 'Close');close.clicked.connect(self.reject);root.addWidget(close)
        self.finished.connect(lambda _:self.clear_passwords())

    def clear_passwords(self):self.current.clear();self.password.clear();self.confirm.clear()

    def target(self):
        row=self.users_table.currentRow()
        item=self.users_table.item(row,0) if row>=0 else None
        return item.text() if item else None

    def selection_changed(self):
        target=self.target()
        if target:self.role.setCurrentText(self.users_table.item(self.users_table.currentRow(),1).text())
        self.reset_button.setEnabled(bool(target and target!=self.name));self.delete_button.setEnabled(bool(target and target!=self.name));self.role_button.setEnabled(bool(target))

    def refresh(self):
        try:
            rows=self.users.list_users(self.session)
            fill_table(self.users_table,[(name,role,'Yes' if required else 'No') for name,role,required in rows])
            fill_table(self.audit_table,self.users.account_history(self.session))
            if rows:self.users_table.selectRow(0)
            self.selection_changed()
        except PermissionError:self.accept()

    def change_password(self):
        try:
            if self.password.text()!=self.confirm.text():raise ValueError('Passwords do not match')
            self.users.change_password(self.session,self.current.text(),self.password.text())
        except (ValueError,PermissionError,sqlite3.Error) as error:
            QMessageBox.warning(self,'Password change failed',str(error));return
        self.clear_passwords()
        QMessageBox.information(self,'Password changed','Password changed. All your sessions are signed out. Sign in again with the new password.')
        self.accept()

    def create_user(self):
        if not self.is_admin:return
        AccountPasswordDialog(self.users,self.session,self).exec();self.refresh()

    def reset_password(self):
        if not self.is_admin:return
        target=self.target()
        if target:AccountPasswordDialog(self.users,self.session,self,target=target).exec();self.refresh()

    def delete_user(self):
        if not self.is_admin:return
        target=self.target()
        if not target:return
        if not self.confirm_action('Delete user',f'Remove access for {target}?\nAll sessions will be signed out. The account and audit history remain archived.'):return
        try:self.users.delete_user(self.session,target)
        except (ValueError,PermissionError,sqlite3.Error) as error:QMessageBox.warning(self,'Delete failed',str(error))
        self.refresh()

    def change_role(self):
        if not self.is_admin:return
        target=self.target();role=self.role.currentText()
        if not target:return
        if not self.confirm_action('Change user role',f'Change {target} to {role}?\nTheir existing sessions will be signed out.'):return
        try:self.users.change_role(self.session,target,role)
        except (ValueError,PermissionError,sqlite3.Error) as error:QMessageBox.warning(self,'Role change failed',str(error))
        self.refresh()

    def confirm_action(self,title,text):
        box=QMessageBox(QMessageBox.Question,title,text,QMessageBox.Yes|QMessageBox.No,self)
        box.setTextFormat(Qt.PlainText);box.setDefaultButton(QMessageBox.No)
        return box.exec()==QMessageBox.Yes
