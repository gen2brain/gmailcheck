#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Author: Milan Nikolic <gen2brain@Gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

__author__ = "Milan Nikolic <gen2brain@gmail.com>"
__license__ = "GPL-3"
__version__ = "0.1.0"

import sys
import time
import base64
import signal
import urllib2
import imaplib
import platform
from uuid import getnode
from optparse import OptionParser
from subprocess import Popen, PIPE
from xml.etree import ElementTree as et
from BaseHTTPServer import BaseHTTPRequestHandler

import sip
sip.setapi('QString', 2)
sip.setapi('QVariant', 2)
from PyQt4.QtGui import QApplication, QSystemTrayIcon, QMenu, QAction, QVBoxLayout, QHBoxLayout
from PyQt4.QtGui import QImage, QWidget, QPixmap, QIcon, QTextBrowser, QDesktopServices
from PyQt4.QtGui import QDialogButtonBox, QLineEdit, QCheckBox, QDialog, QLabel, QMovie
from PyQt4.QtCore import Qt, QSettings, QPoint, QSize, QByteArray, QUrl, QBuffer
from PyQt4.QtCore import pyqtSignal, QTimer, QThreadPool, QRunnable, QMutex

REALM = "New mail feed"
XMLNS = "{http://purl.org/atom/ns#}"
KEY = " ".join(platform.uname()) + str(getnode())
print KEY

HOST = "https://mail.google.com"
URL_ATOM = HOST + "/mail/feed/atom"
URL_HOSTED= HOST + "/a/%s/feed/atom"
URL_OPEN = HOST + "/mail/?fs=1&source=atom#all/%s"
URL_COMPOSE = HOST + "/mail/??view=cm&tf=0#compose"

IMAP_PORT = "993"
IMAP_SERVER = "imap.gmail.com"

LABELS = ["inbox", "firstbeat-inbox"]

class Widget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.tray = Tray(self)
        self.setMinimumSize(QSize(320, 200))
        self.setWindowFlags(Qt.Popup|Qt.FramelessWindowHint)
        self.verticalLayout = QVBoxLayout(self)
        self.verticalLayout.setMargin(1)

        self.text = QTextBrowser(self)
        self.text.setReadOnly(True)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setOpenExternalLinks(True)
        self.verticalLayout.addWidget(self.text)
        self.text.textChanged.connect(self.on_text_changed)
        self.notify = Notify(self)

        self.movie = QMovie()
        dev = QBuffer()
        dev.setData(QByteArray.fromBase64(CHECK_IMAGE))
        dev.open(QBuffer.ReadOnly)
        dev.setParent(self.movie)
        self.movie.setDevice(dev)
        self.movie.frameChanged.connect(self.on_frame_changed)

        self.realized = False
        self.show()

    def showEvent(self, event):
        if not self.realized:
            self.realized = True
            event.ignore()
        x, y = self.get_position()
        self.move(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()

    def get_position(self, size=None):
        if not size: size = self.size()
        tray = self.tray.geometry()
        screen = QApplication.desktop().availableGeometry()
        if tray.left() < screen.left():
            x = screen.left()
            y = screen.height() - size.height()
        elif tray.right() > screen.right():
            x = screen.width() - size.width()
            y = min(screen.height() - size.height(), tray.top())
        elif tray.top() < screen.top():
            x = min(screen.width() - size.width(), tray.left())
            y = screen.top()
        elif tray.bottom() > screen.bottom():
            x = min(screen.width() - size.width(), tray.left())
            y = screen.height() - size.height()
        return x, y

    def on_frame_changed(self):
        self.tray.setIcon(QIcon(self.movie.currentPixmap()))

    def on_text_changed(self):
        if self.text.toPlainText():
            screen = QApplication.desktop().availableGeometry()
            height = self.text.document().size().height()
            if height <= screen.height():
                self.setMinimumHeight(height)
                x, y = self.get_position()
                self.move(x, y)

class Notify(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self)
        self.parent = parent
        self.setMinimumHeight(32)
        self.setMaximumHeight(32)
        self.setWindowFlags(Qt.Popup|Qt.FramelessWindowHint)
        self.verticalLayout = QVBoxLayout(self)
        self.verticalLayout.setMargin(1)
        self.verticalLayout.setContentsMargins(5,5,5,5)
        self.horizontalLayout = QHBoxLayout()
        self.icon = QLabel()
        self.icon.setPixmap(get_icon(MAIL_IMAGE).pixmap(24))
        self.horizontalLayout.addWidget(self.icon)
        self.text = QLabel()
        self.text.setTextFormat(Qt.RichText)
        self.horizontalLayout.addWidget(self.text)
        self.verticalLayout.addLayout(self.horizontalLayout)

    def showEvent(self, event):
        x, y = self.parent.get_position(self.size())
        self.move(x, y)

class Tray(QSystemTrayIcon):
    def __init__(self, parent=None):
        QSystemTrayIcon.__init__(self)
        self.parent = parent
        self.menu = Menu(self.parent)
        icon = get_icon(NO_MAIL_IMAGE)
        self.setIcon(icon)
        self.setVisible(True)
        self.setToolTip(get_tooltip_msg(get_count_msg()))
        self.activated.connect(self.on_activated)
        self.show()

    def on_activated(self, event):
        rect = self.geometry()
        x, y = rect.x(), rect.y()
        if event == self.Context:
            self.setContextMenu(self.menu)
            self.contextMenu().popup(QPoint(x, y))
        elif event in (self.Trigger, self.DoubleClick):
            if self.parent.isVisible():
                self.parent.hide()
            else:
                if self.parent.count:
                    self.parent.show()

class Menu(QMenu):
    def __init__(self, parent=None):
        QMenu.__init__(self)
        self.parent = parent
        action = QAction("&Check mail", self)
        action.triggered.connect(self.parent.check)
        self.addAction(action)

        action = QAction("Compose mail", self)
        action.triggered.connect(self.parent.compose)
        self.addAction(action)

        self.addSeparator()

        action = QAction("&Preferences", self)
        action.triggered.connect(self.parent.preferences)
        self.addAction(action)

        self.addSeparator()

        action = QAction("&Close", self)
        action.triggered.connect(QApplication.quit)
        self.addAction(action)

class Login(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self)
        self.parent = parent
        self.resize(270, 160)
        self.verticalLayout = QVBoxLayout(self)
        self.label_username = QLabel(self)
        self.verticalLayout.addWidget(self.label_username)
        self.username = QLineEdit(self)
        self.verticalLayout.addWidget(self.username)
        self.label_password = QLabel(self)
        self.verticalLayout.addWidget(self.label_password)
        self.password = QLineEdit(self)
        self.password.setEchoMode(QLineEdit.Password)
        self.verticalLayout.addWidget(self.password)
        self.save_password = QCheckBox(self)
        self.verticalLayout.addWidget(self.save_password)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(
                QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.verticalLayout.addWidget(self.buttonBox)
        self.label_username.setBuddy(self.username)
        self.label_password.setBuddy(self.password)
        self.setWindowIcon(get_icon(MAIL_IMAGE))
        self.setWindowTitle("Gmail Login")
        self.label_username.setText("Username")
        self.label_password.setText("Password")
        self.save_password.setText("Save password")
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

class GmailCheck(Widget):
    done = pyqtSignal()
    error = pyqtSignal(str)
    fetching = pyqtSignal()

    def __init__(self, opts):
        Widget.__init__(self)
        self.opts = opts
        self.count = 0
        self.settings = QSettings("gmailcheck", "gmailcheck")

        self.done.connect(self.on_done)
        self.error.connect(self.on_error)
        self.fetching.connect(self.on_fetching)

        self.timer = QTimer()
        self.timer.timeout.connect(self.check)
        self.timer.start(self.settings.value("delay", 120) * 1000)

    def get_login(self):
        if bool(self.settings.value("save_password")):
            self.user = self.settings.value("username")
            self.passwd = decode(KEY, str(self.settings.value("password")))
            if not self.user or not self.passwd:
                self.user, self.passwd = self.get_passwd()
        else:
            self.user, self.passwd = self.get_passwd()

    def get_passwd(self):
        dialog = Login(self)
        dialog.username.setText(
                self.settings.value("username"))
        user, passwd = str(), str()
        if dialog.exec_():
            user = dialog.username.text()
            passwd = dialog.password.text()
            if dialog.save_password.isChecked():
                self.settings.setValue("username", user)
                self.settings.setValue("password", encode(KEY, passwd))
                self.settings.setValue("save_password", 1)
            else:
                self.settings.remove("password")
        return user, passwd

    def start(self):
        self.idmap = {}
        self.entries = []

        pool = QThreadPool()
        pool.setMaxThreadCount(1)

        for label in LABELS:
            feed = Feed(label, self)
            pool.start(feed)
            imap = Imap(label, self)
            pool.start(imap)

        pool.waitForDone()
        self.done.emit()

    def check(self):
        self.get_login()
        if self.passwd:
            self.fetching.emit()
            QTimer.singleShot(500, self.start)

    def compose(self):
        QDesktopServices.openUrl(QUrl(URL_COMPOSE))

    def preferences(self):
        pass

    def execute(self, command=None):
        if command:
            Popen(command, stdout=PIPE, stderr=PIPE, shell=True)

    def popup(self):
        if not self.notify.isVisible():
            self.notify.show()
            QTimer.singleShot(self.settings.value(
                "popup_delay", 5000), self.notify.hide)

    def on_fetching(self):
        if self.isVisible():
            self.hide()
        if self.text.toPlainText():
            self.text.clear()
        if self.movie.state() == QMovie.NotRunning:
            self.movie.start()
        elif self.movie.state() == QMovie.Paused:
            self.movie.setPaused(False)
        self.tray.setToolTip("Checking for new mail...")

    def on_error(self, error):
        if self.movie.state() == QMovie.Running:
            self.movie.setPaused(True)
        self.tray.setIcon(get_icon(ERROR_IMAGE))
        self.tray.setToolTip(error)

    def on_done(self):
        if self.movie.state() == QMovie.Running:
            self.movie.setPaused(True)

        self.text.insertHtml(get_text(self.entries))
        self.notify.text.setText(get_notify(self.entries))

        print self.idmap

        if self.entries:
            count = len(self.entries)
            if count > self.count:
                self.popup()
                self.execute("mplayer -vo null /home/milann/Documents/mail.wav")
            elif count == 0:
                self.execute()
            self.count = count
            self.tray.setIcon(get_icon(MAIL_IMAGE))
        else:
            self.tray.setIcon(get_icon(NO_MAIL_IMAGE))
        self.tray.setToolTip(get_tooltip_msg(
            get_count_msg(len(self.entries))))

class Feed(QRunnable):
    def __init__(self, label, parent=None):
        QRunnable.__init__(self)
        self.label = label
        self.parent = parent
        self.data = None
        self.mutex = QMutex()
        self.setAutoDelete(True)

    def run(self):
        self.check()

    def check(self):
        try:
            self.fetch()
        except (urllib2.URLError, urllib2.HTTPError) as err:
            self.parent.error.emit(str(err))
        else:
            self.read()
            if self.data:
                self.parse()

    def fetch(self):
        auth_handler = urllib2.HTTPBasicAuthHandler()
        auth_handler.add_password(REALM, HOST,
                self.parent.user, self.parent.passwd)
        opener = urllib2.build_opener(auth_handler)
        urllib2.install_opener(opener)
        url = "%s/%s" % (URL_ATOM, self.label) if self.label else URL_ATOM
        self.conn = urllib2.urlopen(url)

    def read(self):
        code = self.conn.getcode()
        if code != 200:
            self.conn.close()
            self.parent.error.emit("HTTP Error %d: %s" % (
                code, BaseHTTPRequestHandler.responses[code]))
        else:
            self.data = self.conn.read()
            self.conn.close()

    def parse(self):
        tree = et.fromstring(self.data)
        for e in tree.findall("%sentry" % XMLNS):
            entry = Entry()
            entry.title = e.find("%stitle" % XMLNS).text
            entry.summary = e.find("%ssummary" % XMLNS).text
            entry.link = e.find("%slink" % XMLNS).attrib["href"]
            entry.modified = e.find("%smodified" % XMLNS).text
            entry.issued = e.find("%sissued" % XMLNS).text
            entry.id = e.find("%sid" % XMLNS).text
            for a in e.findall("%sauthor" % XMLNS):
                entry.author_name = a.find("%sname" % XMLNS).text
                entry.author_email = a.find("%semail" % XMLNS).text

            self.mutex.lock()
            self.parent.entries.append((self.label, entry))
            self.mutex.unlock()

class Imap(QRunnable):
    def __init__(self, label, parent=None):
        QRunnable.__init__(self)
        self.imap = None
        self.label = label
        self.parent = parent
        self.mutex = QMutex()
        self.login()

    def run(self):
        for imap_id in self.get_unread():
            thread_id = self.get_thread_id(imap_id)
            self.mutex.lock()
            self.parent.idmap[thread_id] = imap_id
            self.mutex.unlock()

    def connect(self):
        self.imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)

    def login(self):
        try:
            if not self.imap:
                self.connect()
            auth = self.imap.login(self.parent.user, self.parent.passwd)
            self.logged_in = (auth and auth[0] == "OK")
        except imaplib.IMAP4.error:
            pass

    def logout(self):
        pass

    def get_unread(self):
        self.imap.select(self.label.replace("-", "/"))
        result, unseen = self.imap.search(None, "(UNSEEN)")
        return unseen[0].split()

    def get_thread_id(self, id):
        result, data = self.imap.fetch(id, "(X-GM-THRID BODY.PEEK[HEADER])")
        return data[0][0].split(" ")[2]

class Entry:
	title = ""
	summary = ""
	link = ""
	modified = ""
	issued = ""
	id = ""
	author_name = ""
	author_email = ""

def get_notify(entries):
    names = ""
    for num, data in enumerate(entries):
        label, entry = data
        if num == 0:
            names += entry.author_name
        elif num == len(entries) - 1:
            names += " and %s" % entry.author_name
        else:
            names += ", %s" % entry.author_name
    return "<small>New mail from %s ...</small>" % names

def get_text(entries):
    text = "<small>%s...</small><br/><br/>" % get_count_msg(len(entries))
    for data in entries:
        label, entry = data
        print entry.id
        url = URL_OPEN % format(int(entry.id.split(":")[2]), "x")
        text += "<u><b>%s</b></u>" % entry.title
        if label:
            text += " <small><font color='#006400'>%s</font></small>" % label
        text += "<br/>"
        text += "<b>From:</b> %s<br/>" % entry.author_name
        text += "<a href=\"%s\" style=\"text-decoration:none;\">" % url
        text += "<small><font color=\"#8B0000\">Open</font></small></a><br/>"
        text += "%s<br/><br/>" % entry.summary
    return text

def get_tooltip_msg(msg):
    return "<p style='white-space:pre'>%s (<small>%s</small>)</p>" % (
            msg, time.strftime("%H:%M"))

def get_count_msg(count=0):
    if count == 0:
        return "No new mail"
    elif count == 1:
        return "There is %d new message" % count
    else:
        return "There are %d new messages" % count

def get_icon(data):
    image = QImage()
    bytearr = QByteArray.fromBase64(data)
    image.loadFromData(bytearr, "PNG")
    pixmap = QPixmap.fromImage(image)
    icon = QIcon()
    icon.addPixmap(pixmap)
    return icon

def encode(key, string):
    encoded_chars = []
    for i in xrange(len(string)):
        key_c = key[i % len(key)]
        encoded_c = chr(ord(string[i]) + ord(key_c) % 256)
        encoded_chars.append(encoded_c)
    encoded_string = "".join(encoded_chars)
    return base64.urlsafe_b64encode(encoded_string)

def decode(key, string):
    decoded_chars = []
    string = base64.urlsafe_b64decode(string)
    for i in xrange(len(string)):
        key_c = key[i % len(key)]
        encoded_c = chr(abs(ord(string[i]) - ord(key_c) % 256))
        decoded_chars.append(encoded_c)
    decoded_string = "".join(decoded_chars)
    return decoded_string

MAIL_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAABvFBMVEXCHxCvDQCyAgCxDgC6AwC+DQCzEAC7EAC6HxC6PjKjUUmjWFGjW1quW1OkYVu+Y1u8aF+lZmCmf3uveXSxamO9aWLCBQDBDQDCEgHEFwvEGAfFHAvIHQ7FIA/GIRDIJBTIJxjJKhvMMyTNOivNPjDNQjTNRTjOSTzQRznRSTrAVk7PUUfQTkHRUkbSVUnTWU7VXlLWYFTWZVrYZlrYaV3DamLKbmXZbWLXc2nacGXac2nceW7WeHPcfHOngHuogHzfgXfeg3rghHvgiH6khYKpg4DKioTHn5vWhoLViIXdioPZjIjZlY3fmpTJoJzdopvFpqHNpKDRqaXUqqrcoqHaqqvTs7Tbtbbdurvgi4LgkorjmZHmo53jpqHlqqTorafjsK/gsLDiuLTgvb3pubPpw7/N1NXL2dvbwcLZzs/R1dbW1tvT2Nnc3NzW5OXb4eHd6eriw8Pkzs7ry8ng09Pi3Nzu2dfo3t7wx8LxycXxzcvz0s/y1dL12dX13dv14N7j5OTm5ujl6Ojt4uPq6+vu8O/l8PDt8vLu+vr04uH16Ob45eP46ef57e358O7y9PTz9/j0+/v58/P+/v4RpxciAAAAAXRSTlMAQObYZgAAAAFiS0dEAIgFHUgAAAAJcEhZcwAACxMAAAsTAQCanBgAAAAHdElNRQfdChEQMQeEfrxrAAACFklEQVQ4y93SfW/SQBzAcUYH+MgUda0ddG1R0GTlYYDYYh1bMxcnovKgCIgPmRZMJ9MFDXMjgMc6nM4e94a9UjYT34F+c3/198ld06vN9m9Uq1RxL2rVWrVQeFQpl8vLaUmMRcILgYfm/HB9RVGW08obsA8A6AHQ7Xfv8zzrpajZC1sYDJU0TpaT1W86GJM+nnPzFAbnVROsyLIspUQxnvkMDbN1juMYksTg7BjIopR6HhfxqVIbITRSeI71zQoh2jVtgTvJZKqzEY1GwoJQQz8lc3tS+C67nBboiIvRZAdtRG4KwRvXMnGOYSgyNkIS4bKfGYNYOBLvINQO+QN+nmVYmiTlEYS3ickRnYgghDFAO4ssx7JemqQVCEdQPAZ7QjAYMgEaxr1zNEV6KweGocNb+AgLLAT8QQygodcFknSwmT4AA/0gQTgnIMjzAQwMUH99lL7qf1svNpq9npGYIiywe51j+CEyvjz7CBF8OTT0T8VSswlOwFfeO8ftwdarXTQyDKgPdL1VfKpt/QEcTc5vN0qHcGQMcOZ9dEt5LeEkrO+w4yMpX2H7COq/rCno4hr5GWKygwmYkm5eYw9PWq3NcdrM1AlwuE7V9/v9btNMw73HS71yDNqOabvrQT6Xy2Wf4LLZtewaXo9P2+3WO/y4d9ntvrTk8Xjumi1NWr3odp9b1cY/5QdVVbV3f4cfqpvA9n/0G3KCvN19yOt+AAAAAElFTkSuQmCC"
ERROR_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAABmJLR0QAAAAAAAD5Q7t/AAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3QoaEwcpBPMZiQAAA8RJREFUWMPtlslrFEEUxn/T052FGDTgAho1IZpDUPHqggYEl5NnwYvg/g948yL+CZ7Em3rxFgKKNxUUFPQgLogDGoIGt9hOprunVw+flepZiHjyMg+Kqpl69d6r733vdUFPevKfpWIWs7MU9ToMDLQqOA5Uq5Ak4Hmas8zuJwk0m/b30hIUheY8hyCAOJZeGEr3yBE4cUK+XYDPnylmZiBNwXWt4aKAvj6YnISpKQXS7tzztI5jBZvnMDsLT5/q/0ZDToNAv8MQNmyA+XmK0VEqDlijeS5DcSznSSIDjx7B48c63N9vAzDOk0SB/kGS+/e1jiKLQlnqdfB9rV3zZ5rKkJFmU2jEsW7+4oUO7t0Lo6PSb5dbt2BmptXGz59aV6utyC2nuKxscpRlsHatHBrJMnj5Eu7cgbdvYXDQjjyX83v3rG4YwpcvsGcP7NsntLKsNYUtAaSpNk10hw/DoUPw65eGIdL8PFy/DnfvSs/34do1OY8i6Swu6szBg3D5MoyPa68oOlFzTcSGzWVo9++3eV1cVP6Nodu34ccPeP8enj2zlVCvy96xY3DpEgwNWVQNicspWOZAEIhwntcZxOrVcOOGIB0cFLxxDDdv2sqJIg2Akyfh9GkR01STkWrVkrclBQbiIBB8Zdm5E86ehW3b4NMn7TcaNt9LS3I+MADnzsHFi3Iex9LpBn1HCoLA3sBxOhWnpuDCBd3gwQMRz8CZZTA8DOfPw/HjFsE8t5crk7kjgDIJw7DTeZJof9UqOHoUvn+HJ0/s7datE+wHDtjK8TzbmExA3ZBoqQLfV7TtUaapIH/9WvBfvQqnTomUk5Nw5YrS8/y5UtRoCFHTjo1zs+5AIE3lOIosm03jCEP4+hVqNcE8Pa3bnTkD27fDjh2wZo1sfPwIc3O6yJYtthWvJG6ZSEGgKKPIknJhQc7Hx2FiQgYNpNPTVtdxYOtWld2bN/DuHWzebFv0igGYvp0kmvv7BbXva+zaBSMjcu44llRmLtf18DDs3q2gazUFbRA1KehoxWkqqKNIimmqBlOpyNjIiK2QslMzyqVs9icmhECtprSW81/uA243WBxH34KxMR1uNlvfA2U2G850I9jQkAJ5+FBnKpUVUmCYmmVCoK9Pc7mEuhGq/BgxgZg+YtYr8WCZhL4vmE0JvnoF3761lmQU2QdLuURNgJWKRcesXVfpNCls54ALsHGjevfcnH08LCyo/Mpwd4Pwb1KtwqZNegWZgMfG2gJYv17vsw8fKNph7vbw+FdpR83z9IHrSU96AvAbV5o0+dKP4HEAAAAASUVORK5CYII="
CHECK_IMAGE = "R0lGODlhIAAgAMZEAAQCBAQGBAwKDAwODBQSFBQWFBwaHBweHCQiJCQmJCwqLCwuLDQyNDQ2NDw6PDw+PERCRERGRExKTExOTFRSVFRWVFxaXFxeXGRiZGRmZGxqbGxubHRydHR2dHx6fHx+fISChISGhIyKjIyOjJSSlJSWlJyanJyenKSipKSmpKyqrKyurLSytLS2tLy6vLq8ury+vMTCxMXExcTGxMXGxcrJyszKzMrLyszOzNTS1NTW1Nza3Nze3OTi5OTm5Ozq7Ozu7PTy9PT29Pz6/P///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////yH/C05FVFNDQVBFMi4wAwEAAAAh/hFDcmVhdGVkIHdpdGggR0lNUAAh+QQJBgB/ACwAAAAAIAAgAAAH/oB/goOEhQAGhYmKhRuJh4uQhRUGH4aIhD44kYkGB5aFOJqbhB0GFoSPgz04O6OFCZeCqYI2oq6DLwYOg7M6OD2bJIoOBi+ysbWjDQwYnAnHgqGJOdKDNxAMDSCEk5WPPjY6hDuhOYojyw8yg5WEq6o4yZEbDAwTo6E2wK4VDA+RtcTdEkSjRqR9AxNCmsCwYcNTm+JJrFULh8OLECNN3GhOocdCLmBE8qEwx4cMjSAFdOWDRIYMHzpCymHDBo9IKl5ucCFoBghbf3KwgFetUIwNGTSgIBQCRCsTS3esiDGupsw/PV6KQPiHxYelf0qkEOSCxU1CvoCuuPrHx4dtRIKgCvLBosXHEyDsxgX7ZwYLtqNMiiAkltAKvQNHfLBBSO4goTMGwgBRopDjQS1YkHTVAsTZQZcF8Wjx+WPoj4oK3woEACH5BAkGAH8ALAAAAAAgACAAAAf+gH+Cg4SFBguFiYqFIImHi5CFGgwjhoiEIwImkYUMDZaFAwCchSEMG4SPgxkAEqSFDwyEBbKDAAGvhSgMFIOqfw8AHJwnMYkTDSmCtIIqAAWJPz+EExIdhTEMD4KqBwAkhEE5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"
NO_MAIL_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAQAAADZc7J/AAAAAmJLR0QA/4ePzL8AAAAJcEhZcwAACxMAAAsTAQCanBgAAAAHdElNRQfdChEQMglI68KvAAACqklEQVRIx+3VuW4dVRgH8N+Ze68vJoKYQAEESOI0EQSliYRBRkBDxxuAUGgooM8z8AjwADQUICoWiQokkFAku4DCGBJwFLIJg2P7zsxZKO7xKLLS0YDEKWY98y3/5ZtQ/LPV+M8HGN/rYUERFIR6TxDuHWB7+dvNXqNoFKEWlfQIellE1NsX9TpJq7XqtTAypvv+hnmAIptY9rSRhFxzZ2Otz20IeklUsOa58mhoSA9FRZIlxZ5LvrPvPjQaQTDV+8y6RpJFQaOxY3veQpBFjaKtmX/wpxUntYpiIvvUuixJ+orMQR1jslavMbbkhrGg+MVtrzgLZj60JimKmadwVaeRD2gMiiLiJSv27Ep6N33kS8WO962Jsl7nCe96fMCmshAlvYSJVSNf2avof+G2qy5XFpIz3nFEqzPWV1LH0GoFWcLz7vexbQuS6GtpeHPem6ayjGJUqxhTRD1SjXnO1Cd+08iKrEhGVlzQ60yFCmI4wCBrtbWJ+TrjDaf0elGSLHjV62Z6STEbVDpUkKra5jKOoiWrtv2uYOpFL9gRTTSVvjika+Y66MRaVJLcsW7XRSsaSy447ZItnX2tLCjy4IuxKo4oIEuu23TUecFbTnjGw5JNV9zxmN7C8PHcZmOyvlpmT/KrK044rZdkL+vsK05atGHPk6aDNwcWsijKGns2/OGcJbNK1249d4561s9+sqzcZfEybyFWXC875axFnYgs19bmMI8su2XLfg0R0MxZmNsjO2ZZ5y/RnJtCvc51z4OO+ObwQAmChGBBr1MU7YDy7K7NQTQ6NJnGxErioh/dqkLtB5RTLVgdLRM3FUHQHdj5+HsrF7fMcM31ob9Sj2GYkgfSfcCiIDquQSjoXCsz9Ic4Docom4ea1KkZPPL2sQ/C/3+mf0GAvwHOBGIjZeQ/2gAAAABJRU5ErkJggg=="

def main():
    usage = "usage: %prog <options>"
    parser = OptionParser(usage=usage,
            version="GmailCheck Version %s" % __version__)
    parser.add_option("--hosted", action="store", dest="hosted", type="string",
            default="", help="hosted domain", metavar="<arg>")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    opts, args = parser.parse_args()
    GmailCheck(opts)

    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
