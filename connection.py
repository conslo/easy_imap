from imaplib import IMAP4_SSL
from re import compile

list_response_pattern = compile(r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)')


def parse_list_response(line):
    flags, delimiter, mailbox_name = list_response_pattern.match(line).groups()
    mailbox_name = mailbox_name.strip('"')
    return flags, delimiter, mailbox_name


class BadReturnStatus(Exception):
    pass


class ReadOnlyException(Exception):
    pass


def _ok(ok):
    if ok != "OK":
        raise BadReturnStatus("status was {}".format(ok))


class Connection(object):

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        password = kwargs.pop("password", None)
        self.mailbox = 'INBOX'
        self.readonly = False

        self.parent = IMAP4_SSL(*args, **kwargs)

        if user is not None and password is not None:
            self.login(user, password)

    # Using composition and a prefix instead of inheritance allows us to create replacements piece by piece,
    # yet still allows use of non-replaced methods, without causing any comparability breaks in between.
    def __getattr__(self, name):
        if name.startswith("_") and hasattr(self.parent, name[1:]):
            return getattr(self.parent, name[1:])
        else:
            raise AttributeError

    def login(self, user, password):
        ok, value = self._login(user, password)
        _ok(ok)

        return value[0]

    def list(self, *args, **kwargs):
        boxes = {}
        ok, boxlist = self._list(*args, **kwargs)
        _ok(ok)

        for boxline in boxlist:
            flags, delimiter, name = parse_list_response(boxline)
            thisbox = {
                'flags': flags,
                'delimeter': delimiter
            }
            boxes[name] = thisbox

        return boxes

    def select(self, mailbox="INBOX", readonly=False):
        self.switch(mailbox, readonly)

        return MailBox(self, mailbox, readonly)

    def switch(self, mailbox="INBOX", readonly=False):
        ok, messages = self._select(mailbox, readonly)
        _ok(ok)
        self.mailbox = mailbox
        self.readonly = self.readonly

    def search(self, *args, **kwargs):
        charset = kwargs.pop("charset", None)
        ok, results = self._search(charset, *args, **kwargs)
        _ok(ok)
        if results[0] == '':
            return []
        else:
            ids = results[0].split(' ')
            return ids

    def fetch(self, nums, *args, **kwargs):
        numstr = ' '.join(str(n) for n in nums)
        command = "(" + " ".join(args) + ")"
        ok, result = self._fetch(numstr, command, **kwargs)
        _ok(ok)
        return result

    def store(self, messages, flags, command="+", silent=False):
        command += "FLAGS"
        if silent:
            command += ".SILENT"
        new_flag_list = []
        for message in messages:
            ok, new_flags = self._store(message, command, flags)
            _ok(ok)
            new_flag_list.append(new_flags)
        return new_flag_list


class MailBox(object):

    def __init__(self, connection, mailbox, readonly):
        self.connection = connection
        self._mailbox, self._readonly = mailbox, readonly

    def _select(self):
        if self.connection.mailbox != self._mailbox:
            self.connection.switch(self._mailbox, self._readonly)

    def search(self, *args, **kwargs):
        self._select()
        messages = []
        for message in self.connection.search(*args, **kwargs):
            messages.append(Message(self, message))
        return messages

    def fetch(self, nums, *args):
        self._select()
        return self.connection.fetch(nums, *args)

    def store(self, *args, **kwargs):
        if self._readonly:
            raise ReadOnlyException
        self._select()
        return self.connection.store(*args, **kwargs)


class Message(MailBox):

    def __init__(self, inherit, num):
        super(Message, self).__init__(inherit.connection, inherit._mailbox, inherit._readonly)
        self.num = num

    def fetch(self, *args):
        return super(Message, self).fetch(str(self.num), *args)

    def store(self, flags, command="+", silent=False):
        new_flags = super(Message, self).store([self.num], flags, command=command, silent=silent)
        return new_flags[0]
