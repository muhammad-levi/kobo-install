# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
import os
import shutil
import sys
import tempfile

from helpers.cli import CLI
from helpers.command import Command
from helpers.config import Config
from helpers.template import Template


class Setup:

    @classmethod
    def clone_kobodocker(cls, config):
        """
            Args:
                config (helpers.config.Config)
        """
        dict_ = config.get_dict_()
        do_update = config.first_time

        if not os.path.isdir(os.path.join(dict_['kobodocker_path'], '.git')):
            # Move unique id file to /tmp in order to clone without errors
            # (e.g. not empty directory)
            tmp_dirpath = tempfile.mkdtemp()
            shutil.move(os.path.join(dict_['kobodocker_path'],
                                     Config.UNIQUE_ID_FILE),
                        os.path.join(tmp_dirpath, Config.UNIQUE_ID_FILE))

            # clone project
            git_command = [
                'git', 'clone', 'https://github.com/kobotoolbox/kobo-docker',
                dict_['kobodocker_path']
            ]
            CLI.run_command(git_command, cwd=os.path.dirname(
                dict_['kobodocker_path']))

            shutil.move(os.path.join(tmp_dirpath, Config.UNIQUE_ID_FILE),
                        os.path.join(dict_['kobodocker_path'],
                                     Config.UNIQUE_ID_FILE))
            shutil.rmtree(tmp_dirpath)
            do_update = True  # Force update

        if do_update:
            cls.update_kobodocker(dict_)

    @classmethod
    def post_update(cls, cron):

        config = Config()

        # When `cron` is True, we want to bypass question and just recreate
        # YML and environment files from new templates
        if cron is True:
            current_dict = config.get_template()
            current_dict.update(config.get_dict())
            config.set_config(current_dict)
            Template.render(config, force=True)
            sys.exit(0)

        CLI.colored_print('╔══════════════════════════════════════════════════════╗',
                          CLI.COLOR_WARNING)
        CLI.colored_print('║ After an update, it is strongly recommended to run   ║',
                          CLI.COLOR_WARNING)
        CLI.colored_print('║ `./run.py --setup` to regenerate environment files.  ║',
                          CLI.COLOR_WARNING)
        CLI.colored_print('╚══════════════════════════════════════════════════════╝',
                          CLI.COLOR_WARNING)

        CLI.colored_print('Do you want to proceed?', CLI.COLOR_SUCCESS)
        CLI.colored_print('\t1) Yes')
        CLI.colored_print('\t2) No')
        response = CLI.get_response(default=True)
        if response is True:
            current_dict = config.build()
            Template.render(config)
            config.init_letsencrypt()
            Setup.update_hosts(current_dict)

            CLI.colored_print('Do you want to (re)start containers?',
                              CLI.COLOR_SUCCESS)
            CLI.colored_print('\t1) Yes')
            CLI.colored_print('\t2) No')
            response = CLI.get_response(default=True)
            if response is True:
                Command.start()

    @staticmethod
    def update_kobodocker(dict_=None):
        """
            Args:
                dict_ (dict): Dictionary provided by `Config.get_dict()`
        """
        if not dict_:
            config = Config()
            dict_ = config.get_dict()

        # fetch new tags and prune
        git_command = ['git', 'fetch', '-p']
        CLI.run_command(git_command, cwd=dict_['kobodocker_path'])

        # checkout branch
        git_command = ['git', 'checkout', '--force', Config.KOBO_DOCKER_BRANCH]
        CLI.run_command(git_command, cwd=dict_['kobodocker_path'])

        # update code
        git_command = ['git', 'pull', 'origin', Config.KOBO_DOCKER_BRANCH]
        CLI.run_command(git_command, cwd=dict_['kobodocker_path'])

    @staticmethod
    def update_koboinstall(version):
        # fetch new tags and prune
        git_fetch_prune_command = ['git', 'fetch', '-p']
        CLI.run_command(git_fetch_prune_command)

        # checkout branch
        git_command = ['git', 'checkout', '--force', version]
        CLI.run_command(git_command)

        # update code
        git_command = ['git', 'pull', 'origin', version]
        CLI.run_command(git_command)

    @classmethod
    def update_hosts(cls, dict_):
        """
            Args:
                dict_ (dict): Dictionary provided by `Config.get_dict()`
        """
        if dict_['local_installation'] is True:
            start_sentence = '### (BEGIN) KoBoToolbox local routes'
            end_sentence = '### (END) KoBoToolbox local routes'

            with open('/etc/hosts', 'r') as f:
                tmp_host = f.read()

            start_position = tmp_host.find(start_sentence)
            end_position = tmp_host.find(end_sentence)

            if start_position > -1:
                tmp_host = tmp_host[0: start_position] \
                           + tmp_host[end_position + len(end_sentence) + 1:]

            routes = '{ip_address}  ' \
                     '{kpi_subdomain}.{public_domain_name} ' \
                     '{kc_subdomain}.{public_domain_name} ' \
                     '{ee_subdomain}.{public_domain_name}'.format(
                        ip_address=dict_['local_interface_ip'],
                        public_domain_name=dict_['public_domain_name'],
                        kpi_subdomain=dict_['kpi_subdomain'],
                        kc_subdomain=dict_['kc_subdomain'],
                        ee_subdomain=dict_['ee_subdomain']
                     )

            tmp_host = ('{bof}'
                        '\n{start_sentence}'
                        '\n{routes}'
                        '\n{end_sentence}'
                        ).format(
                bof=tmp_host.strip(),
                start_sentence=start_sentence,
                routes=routes,
                end_sentence=end_sentence
            )

            with open('/tmp/etchosts', 'w') as f:
                f.write(tmp_host)

            if dict_['review_host'] is True:
                CLI.colored_print('╔═══════════════════════════════════════════════════════════════════╗',
                                  CLI.COLOR_WARNING)
                CLI.colored_print('║ Administrative privileges are required to update your /etc/hosts. ║',
                                  CLI.COLOR_WARNING)
                CLI.colored_print('╚═══════════════════════════════════════════════════════════════════╝',
                                  CLI.COLOR_WARNING)
                CLI.colored_print('Do you want to review your /etc/hosts file before overwriting it?',
                                  CLI.COLOR_SUCCESS)
                CLI.colored_print('\t1) Yes')
                CLI.colored_print('\t2) No')
                dict_['review_host'] = CLI.get_response(
                    default=dict_['review_host'])

                if dict_['review_host'] is True:
                    print(tmp_host)
                    CLI.colored_input('Press any keys when ready')

                # Save 'review_host'
                config = Config()
                config.write_config()

            cmd = 'sudo mv /etc/hosts /etc/hosts.old ' \
                  '&& sudo mv /tmp/etchosts /etc/hosts'
            return_value = os.system(cmd)
            if return_value != 0:
                sys.exit(1)

    @staticmethod
    def validate_already_run():
        """
        Validates that Setup has been run at least once and kobo-docker has been
        pulled and checked out before going further.
        """

        config = Config()
        dict_ = config.dict_()

        def display_error_message(message):
            max_chars_count = 51
            message_length = len(message)
            spacer = ' ' * (max_chars_count - message_length)

            CLI.colored_print('╔═════════════════════════════════════════════════════╗',
                              CLI.COLOR_ERROR)
            CLI.colored_print('║ {}{} ║'.format(message, spacer),
                              CLI.COLOR_ERROR)
            CLI.colored_print('║ Please run `./run.py --setup` first .               ║',
                              CLI.COLOR_ERROR)
            CLI.colored_print('╚═════════════════════════════════════════════════════╝',
                              CLI.COLOR_ERROR)
            sys.exit(1)

        try:
            dict_['kobodocker_path']
        except KeyError:
            display_error_message('No configuration file found.')

        if not os.path.isdir(os.path.join(dict_['kobodocker_path'], '.git')):
            display_error_message('`kobo-docker` repository is missing!')
