class HostInfo:
    def __init__(
        self,
        public_ip=None,
        private_ip=None,
        ssh_user=None,
        ssh_key_file=None,
        category=None,
        offset=None,
    ):
        self.public_ip = public_ip
        self.private_ip = private_ip
        self.ssh_user = ssh_user
        self.ssh_key_file = ssh_key_file
        self.category = category
        self.offset = offset

    def __eq__(self, other):
        if not isinstance(other, HostInfo):
            return False

        return (
            self.public_ip == other.public_ip
            and self.private_ip == self.private_ip
            and self.ssh_user == other.ssh_user
            and self.ssh_key_file == other.ssh_key_file
            and self.category == other.category
            and self.offset == other.offset
        )

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "HostInfo({}, {}, {}, {}, {}, {})".format(
            self.public_ip,
            self.private_ip,
            self.ssh_user,
            self.ssh_key_file,
            self.category,
            self.offset,
        )

    def __hash__(self):
        return hash(self.__repr__())

    def __copy__(self):
        return HostInfo(
            public_ip=self.public_ip,
            private_ip=self.private_ip,
            ssh_user=self.ssh_user,
            ssh_key_file=self.ssh_key_file,
            category=self.category,
            offset=self.offset,
        )
