#!/usr/bin/env python3
from impacket.examples.ntlmrelayx.attacks.ldapattack import LDAPAttack
from impacket.examples.ntlmrelayx.utils.config import NTLMRelayxConfig

from pywerview.modules.addcomputer import ADDCOMPUTER
from pywerview.utils.helpers import *

import ldap3
import logging
import re

class PywerView:

    def __init__(self,ldap_server, ldap_session, args):
        self.ldap_server = ldap_server
        self.ldap_session = ldap_session
        self.args = args

        cnf = ldapdomaindump.domainDumpConfig()
        cnf.basepath = None
        self.domain_dumper = ldapdomaindump.domainDumper(self.ldap_server, self.ldap_session, cnf)
        self.root_dn = self.domain_dumper.getRoot()
        self.fqdn = ".".join(self.root_dn.replace("DC=","").split(","))

    def get_domainuser(self, args=None, properties=['cn','name','sAMAccountName','distinguishedName','mail','description','lastLogoff','lastLogon','memberof','objectSid','userPrincipalName'], identity='*'):
        if args:
            if args.preauthnotrequired:
                ldap_filter = f'(&(samAccountType=805306368)(userAccountControl:1.2.840.113556.1.4.803:=4194304)(sAMAccountName={identity}))'
            elif args.admincount:
                ldap_filter = f'(&(samAccountType=805306368)(admincount=1)(sAMAccountName={identity}))'
            elif args.allowdelegation:
                ldap_filter = f'(&(samAccountType=805306368)!(userAccountControl:1.2.840.113556.1.4.803:=1048574)(sAMAccountName={identity}))'
            elif args.trustedtoauth:
                ldap_filter = f'(&(samAccountType=805306368)(|(samAccountName={identity}))(msds-allowedtodelegateto=*))'
            elif args.spn:
                ldap_filter = f'(&(samAccountType=805306368)(servicePrincipalName=*)(sAMAccountName={identity}))'
            else:
                ldap_filter = f'(&(samAccountType=805306368)(sAMAccountName={identity}))'
        else:
            ldap_filter = f'(&(samAccountType=805306368)(sAMAccountName={identity}))'

        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def get_domaincontroller(self, args=None, properties='*', identity='*'):
        ldap_filter = f'(userAccountControl:1.2.840.113556.1.4.803:=8192)'
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def get_domainobject(self, args=None, properties='*', identity='*'):
        ldap_filter = f'(&(|(|(samAccountName={identity})(name={identity})(displayname={identity}))))'
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries
    
    def get_domaincomputer(self, args=None, properties='*', identity='*'):
        if args:
            if args.unconstrained:
                ldap_filter = f'(&(samAccountType=805306369)(userAccountControl:1.2.840.113556.1.4.803:=524288)(name={identity}))'
            elif args.trustedtoauth:
                ldap_filter = f'(&(samAccountType=805306369)(|(name={identity}))(msds-allowedtodelegateto=*))'
            elif args.laps:
                ldap_filter = f'(&(objectCategory=computer)(ms-MCS-AdmPwd=*)(sAMAccountName={identity}))'
            else:
                ldap_filter = f'(&(samAccountType=805306369)(name={identity}))'
        else:
            ldap_filter = f'(&(samAccountType=805306369)(name={identity}))'

        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def get_domaingroup(self, args=None, properties='*', identity='*'):
        ldap_filter = f'(&(objectCategory=group)(|(|(samAccountName={identity})(name={identity}))))'
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def get_domaingpo(self, args=None, properties='*', identity='*'):
        ldap_filter = f'(&(objectCategory=groupPolicyContainer)(cn={identity}))'
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def get_domainou(self, args=None, properties='*', identity='*'):
        if args.gplink is None:
            ldap_filter = f'(&(objectCategory=organizationalUnit)(|(name={identity})))'
        else:
            print("masuk bawah")
            ldap_filter = f'(&(objectCategory=organizationalUnit)(|(name={identity}))(gplink={args.gplink}))'
        
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries
    
    def get_domaintrust(self, args=None, properties='*', identity='*'):
        ldap_filter = f'(objectClass=trustedDomain)'
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def get_domain(self, args=None, properties='*', identity='*'):
        ldap_filter = f'(objectClass=domain)'
        self.ldap_session.search(self.root_dn,ldap_filter,attributes=properties)
        return self.ldap_session.entries

    def add_domaingroupmember(self, identity, members, args=None):
        group_entry = self.get_domaingroup(identity=identity,properties='distinguishedName')
        user_entry = self.get_domainuser(identity=members,properties='distinguishedName')
        targetobject = group_entry[0]
        userobject = user_entry[0]
        succeeded = self.ldap_session.modify(targetobject.entry_dn,{'member': [(ldap3.MODIFY_ADD, [userobject.entry_dn])]})
        if not succeeded:
            print(self.ldap_session.result['message'])
        return succeeded

    def add_domainobjectacl(self, targetidentity, principalidentity, rights, args=None):
        c = NTLMRelayxConfig()
        c.target = 'range.net'

        logging.info('Initializing LDAPAttack()')
        la = LDAPAttack(c, self.ldap_session, principalidentity.replace('\\', '/'))
        la.aclAttack(targetidentity, self.domain_dumper)
        return True

    def remove_domaincomputer(self,username,password,domain,computer_name,args):
        if computer_name[-1] != '$':
            computer_name += '$'

        dcinfo = get_dc_host(self.ldap_session, self.domain_dumper, args)
        if len(dcinfo)== 0:
            logging.error("Cannot get domain info")
            exit()
        c_key = 0
        dcs = list(dcinfo.keys())
        if len(dcs) > 1:
            logging.info('We have more than one target, Pls choices the hostname of the -dc-ip you input.')
            cnt = 0
            for name in dcs:
                logging.info(f"{cnt}: {name}")
                cnt += 1
            while True:
                try:
                    c_key = int(input(">>> Your choice: "))
                    if c_key in range(len(dcs)):
                        break
                except Exception:
                    pass
        dc_host = dcs[c_key].lower()

        setattr(self.args, "dc_host", dc_host)
        setattr(self.args, "delete", True)

        if self.args.use_ldaps:
            setattr(self.args, "method", "LDAPS")
        else:
            setattr(self.args, "method", "SAMR")

        # Creating Machine Account
        addmachineaccount = ADDCOMPUTER(
            username,
            password,
            domain,
            self.args,
            computer_name)
        addmachineaccount.run()

        if len(self.get_domainobject(identity=computer_name)) == 0:
            return True
        else:
            return False


    def add_domaincomputer(self, username, password, domain, computer_name, computer_pass):
        if computer_name[-1] != '$':
            computer_name += '$'

        dcinfo = get_dc_host(self.ldap_session, self.domain_dumper, self.args)
        if len(dcinfo)== 0:
            logging.error("Cannot get domain info")
            exit()
        c_key = 0
        dcs = list(dcinfo.keys())
        if len(dcs) > 1:
            logging.info('We have more than one target, Pls choices the hostname of the -dc-ip you input.')
            cnt = 0
            for name in dcs:
                logging.info(f"{cnt}: {name}")
                cnt += 1
            while True:
                try:
                    c_key = int(input(">>> Your choice: "))
                    if c_key in range(len(dcs)):
                        break
                except Exception:
                    pass
        dc_host = dcs[c_key].lower()

        setattr(self.args, "dc_host", dc_host)
        setattr(self.args, "delete", False)

        if self.args.use_ldaps:
            setattr(self.args, "method", "LDAPS")
        else:
            setattr(self.args, "method", "SAMR")
            

        # Creating Machine Account
        addmachineaccount = ADDCOMPUTER(
            username,
            password,
            domain,
            self.args,
            computer_name,
            computer_pass)
        addmachineaccount.run()


        if self.get_domainobject(identity=computer_name)[0].entry_dn:
            return True
        else:
            return False

    def set_domainobject(self,identity, args=None):
        targetobject = self.get_domainobject(identity=identity)
        if len(targetobject) > 1:
            logging.error('More than one object found')
            return False

        if args.clear:
            logging.info('Printing object before clearing')
            logging.info(f'Found target object {targetobject[0].entry_dn}')
            succeeded = self.ldap_session.modify(targetobject[0].entry_dn, {args.clear: [(ldap3.MODIFY_REPLACE,[])]})
        elif args.set:
            attrs = self.parse_object(args.set)
            logging.info('Printing object before modifying')
            logging.info(f'Found target object {targetobject[0].entry_dn}')
            succeeded = self.ldap_session.modify(targetobject[0].entry_dn, {attrs['attr']:[(ldap3.MODIFY_REPLACE,[attrs['val']])]})

        if not succeeded:
            logging.error(self.ldap_session.result['message'])

        return succeeded

    def parse_object(self,obj):
        attrs = dict()
        regex = r'\{(.*?)\}'
        res = re.search(regex,obj)
        dd = res.group(1).replace("'","").replace('"','').split("=")
        attrs['attr'] = dd[0]
        attrs['val'] = dd[1]
        return attrs
