import re
import git
from concurrent.futures import ThreadPoolExecutor
from tornado import gen,concurrent
from  tornado.httpclient import AsyncHTTPClient
import os
import os.path
from urllib.parse import urlparse
import yaml
import socket


class GitMixin:
    STATE_VARS = ['_repo_url', '_repo_dir', '_repo_pointer', '_processed_repo_url',
            '_protocol', '_service', '_owner', '_repo', '_token', '_repo_sha', '_branch_name']

    def parse_url(self, repo_url, tmp_dir=None):
        """parse repo_url to parts:
        _processed: url to clone from
        _repo_pointer: position to reset"""

        self._repo_url = repo_url
        self._repo_dir = tmp_dir
        self._repo_pointer = None
        if re.search(r'@[\w/]+?$', repo_url):
            self._processed_repo_url, self._repo_pointer = repo_url.rsplit('@', 1)
            if self._repo_pointer.endswith('/'):
                self._repo_pointer = self._repo_pointer[:-1]
        else:
            parts = re.match(
                r'(^.+?://[^/]+/[^/]+/.+?)(?:/|$)(tree|commits?)?(/[^/]+)?', # github and bitbucket
                repo_url
            )
            if not parts:
                raise ValueError('Incorrect repository url')
            self._processed_repo_url = parts.group(1)
            if parts.group(3):
                self._repo_pointer = parts.group(3)[1:]
        if self._processed_repo_url.endswith('.git'):
            self._processed_repo_url = self._processed_repo_url[:-4]
        if not self._repo_pointer:
            self._repo_pointer = 'HEAD'

        url_parts = re.match(r'^(.+?)://([^/]+)/([^/]+)/(.+)/?$', self._processed_repo_url)
        if not url_parts:
            raise ValueError('Incorrect repository url')
        self._protocol, self._service, self._owner, self._repo = url_parts.groups()
        self._token = None

        for not_supported_protocol in ('ssh',):
            if not_supported_protocol in self._protocol.lower():
                raise ValueError("%s isn't supported yet" % not_supported_protocol)

        if '@' in self._service:
            token, self._service = self._service.split('@')
            if re.match(r'\w+:x-oauth-basic', token):
                token, _ = token.split(':')
            self._token = token
            self._processed_repo_url = '{proto}://{service}/{owner}/{repo}'.format(
                proto=self._protocol,
                service=self._service,
                owner=self._owner,
                repo=self._repo
            )

    _git_executor = None
    @property
    def git_executor(self):
        """single global git executor"""
        cls = self.__class__
        if cls._git_executor is None:
            cls._git_executor = ThreadPoolExecutor(20)
        return cls._git_executor

    _git_client = None
    @property
    def git_client(self):
        """single global git client instance"""
        cls = self.__class__
        if cls._git_client is None:
            cls._git_client = git.Git()
        return cls._git_client

    def _git(self, method, *args, **kwargs):
        """wrapper for calling git methods

        to be passed to ThreadPoolExecutor
        """
        m = getattr(self.git_client, method)
        return m(*args, **kwargs)

    def git(self, method, *args, **kwargs):
        """Call a git method in a background thread

        returns a Future
        """
        return self.git_executor.submit(self._git, method, *args, **kwargs)

    @gen.coroutine
    def prepare_local_repo(self):
        """Returns False if there is no Dockerfile in repo

        True otherwise
        """
        clone_url = self.repo_url_with_token
        yield self.git('clone', clone_url, self._repo_dir)
        repo = git.Repo(self._repo_dir)
        repo.git.reset('--hard', self._repo_pointer)
        self._repo_sha = repo.rev_parse('HEAD').hexsha
        self._branch_name = repo.active_branch.name

        dockerfile_path = os.path.join(self._repo_dir, 'Dockerfile')
        if not os.path.isfile(dockerfile_path):
            if not os.environ.get('DEFAULT_DOCKER_IMAGE'):
                raise Exception('No dockerfile in repository')
            with open(dockerfile_path, 'w') as fout:
                fout.writelines([
                    'FROM %s\n' % os.environ['DEFAULT_DOCKER_IMAGE'],
                    'MAINTAINER Alexander Tiunov <astiunov@yandex-team.ru>'
                ])
            return False
        else:
            return True

    @gen.coroutine
    def prepare_everware_yml(self, _user_log):
        self.directory_data = self._repo_dir + "-data"
        self._user_log = _user_log
        os.mkdir(self.directory_data)
        self.everware_yml_param["directory_data"] = self.directory_data
        everware_yml_path = os.path.join(self._repo_dir, 'everware.yml')
        if os.path.isfile(everware_yml_path):
            with open(everware_yml_path) as file:
                text = yaml.load(file)
            all_data = []
            for element in text:
                all_data += text.get(element).get("data")
            for data in all_data:
                if type(data) == dict:
                    url = data.get("url")
                    ssl = data.get("ssl")
                else:
                    url = data
                url_struct = urlparse(url)
                self._user_log.append(({'text': "Start download from %s" % url_struct.geturl(), 'level': 2}))
                if url_struct.scheme == "root":
                    yield self.download_xrootd(url_struct, ssl)
                else:
                    yield self.download_http(url_struct, ssl)

        self.everware_yml_param["user_log"] = self._user_log
        return self.everware_yml_param

    @property
    def escaped_repo_url(self):
        repo_url = re.sub(r'^.+?://', '', self._processed_repo_url)
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        trans = str.maketrans(':/-.', "____")
        repo_url = repo_url.translate(trans).lower()
        return re.sub(r'_+', '_', repo_url)

    @property
    def repo_url(self):
        return self._processed_repo_url

    @property
    def commit_sha(self):
        return self._repo_sha

    @property
    def branch_name(self):
        return self._branch_name

    @property
    def repo(self):
        return self._repo

    @property
    def owner(self):
        return self._owner

    @property
    def service(self):
        return self._service

    @property
    def token(self):
        return self._token

    @property
    def repo_url_with_token(self):
        cur_service = self._service

        token = None
        if hasattr(self.user, 'token'):
            token = self.user.token
        elif hasattr(self.authenticator, 'test_token'):
            token = self.authenticator.test_token

        if token and self.user.escaped_name:
            cur_service = self.user.escaped_name + ':' + token + '@' + self._service

        return '{proto}://{service}/{owner}/{repo}'.format(
            proto=self._protocol,
            service=cur_service,
            owner=self._owner,
            repo=self._repo
        )

    def get_state(self):
        result = {key: getattr(self, key, '') for key in self.STATE_VARS}
        return result

    def load_state(self, state):
        for key in self.STATE_VARS:
            if key in state:
                setattr(self, key, state[key])

    def download_file(self, url):
        url_struct = urlparse(url)
        if url_struct.scheme == "root":
            self.download_xrootd(self, url_struct)
        else:
            self.download_http(self, url_struct)

    @concurrent.run_on_executor(executor='_git_executor')
    def download_xrootd(self, url_struct, ssl):
        try:
            from sh import xrdcp
        except:
            self.log.info("Sorry, but everware doesn't support xrootd now")
            return
        try:
            self.log.info("Downloading from xrootd server %s" % url_struct.hostname)
            xrdcp("-DIConnectionRetry 1", "-r", url_struct.geturl(), self.directory_data)
            self.log.info("Downloaded")
            self._user_log.append(({'text': "Successfully downloaded from %s" % url_struct.geturl(), 'level': 2}))
        except:
            self.log.info("Cannot download")
            self._user_log.append(({'text': "Fail to download from %s" % url_struct.geturl(), 'level': 2}))
        return

    @gen.coroutine
    def download_http(self, url_struct, ssl):
        http_client = AsyncHTTPClient()
        filename = url_struct.path.split("/")[-1]
        if len(filename) == 0:
            filename = url_struct.path.split("/")[-2]
        #folder with data files is deleted after container removing
        if ssl:
            pass
        try:
            self.log.info("Downloading from http server %s" % url_struct.hostname)
            response = yield http_client.fetch(url_struct.geturl())
            with open(self.directory_data + '/' + filename, "ab") as f:
                f.write(response.body)
            self.log.info("Downloaded")
            self._user_log.append(({'text': "Successfully downloaded from %s" % url_struct.geturl(), 'level': 2}))
            http_client.close()
        except:
            self.log.info("Something went wrong during downloading from %s " % url_struct.hostname)
            pass


