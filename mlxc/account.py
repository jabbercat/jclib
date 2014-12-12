
class Account:
    def __init__(self, name, client_jid, password=None):
        self.name = name or str(client_jid)
        self.client_jid = client_jid
        self.password = password
