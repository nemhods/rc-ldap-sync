#!/usr/bin/env python3

from rocketchat_API.rocketchat import RocketChat
from ldap3 import Server, Connection, ALL

RC_URL = 'https://rocketchat.example.com'
RC_ADMIN_ACCOUNT = "my_rc_admin"
RC_ADMIN_PASSWORD = '12345'

LDAP_SERVER_IP = "192.168.1.1"
LDAP_BIND_ACCOUNT = 'CN=LdapAccess,OU=FunctionalAccounts,DC=acme,DC=com'
LDAP_BIND_PASSWORD = '12345'
LDAP_SEARCH_BASE = 'OU=Users,DC=acme,DC=com'

ldap_server = Server(LDAP_SERVER_IP, get_info=ALL)
ldap_conn = Connection(ldap_server, LDAP_BIND_ACCOUNT, LDAP_BIND_PASSWORD, auto_bind=True)
rc = RocketChat(RC_ADMIN_ACCOUNT, RC_ADMIN_PASSWORD, server_url=RC_URL)

channel_mappings = [
    {
        'ldap_query': '(&(objectclass=person))', # query to find users to add
        'channel': 'testchannel', # machine-readable ("slugified") channel name (see channel details to find this)
        'private': True, # set to True if the target channel is a private group. rcadmin must be member of this group to manage it!
        'apply': True, # if this is False, the script will not actually apply the new member list, just print the changes! use this to test your mapping
        'additional_users': [ # list of users that should be in the channel, even if they are not in the ldap query
            'my_rc_admin'
        ]
    }
]

def main():
    # get full user list of rocket.chat server
    rc_users = {user.get("username"):user.get("_id")for user in rc.users_list(count=0).json()['users']}

    for mapping in channel_mappings:
        print(f"\n\nmanaging channel {mapping.get('channel')} (apply: {not mapping.get('apply')})")
        
        try:
            if mapping.get("private"):
                # channel is private. this is a "group" in rocket.chat terms, and we need to use different API methods
                rc_channel = rc.groups_list_all(query=f'{{"name": {{"$regex":"{mapping.get("channel")}"}}}}').json()['groups'][0]
                rc_channel_id = rc_channel.get("_id")
                current_users = [user.get("username") for user in rc.groups_members(rc_channel_id, count=0).json()['members']]
            else:
                rc_channel = rc.channels_list(query=f'{{"name": {{"$regex":"{mapping.get("channel")}"}}}}').json()['channels'][0]
                rc_channel_id = rc_channel.get("_id")
                current_users = [user.get("username") for user in rc.channels_members(rc_channel_id, count=0).json()['members']]
        except IndexError:
            print("> ERROR: could not find channel. check the spelling (use machine-readable name of channel) as well as the private flag.")
            continue
        except KeyError:
            print("> ERROR: could not get channel members. rcadmin must be in the group to manage it!")
            continue

        print(f"> found channel ID {mapping.get('channel')} = {rc_channel_id}")
        
        desired_users = ldap_get_usernames(mapping.get("ldap_query")) + mapping.get("additional_users")
        unmatched_users = [user for user in desired_users if not user in rc_users]
        if len(unmatched_users) > 0:
            print(f"> WARNING: the following users don't yet have a rocketchat account and will be ignored:\n{unmatched_users}")
        desired_users = [user for user in desired_users if not user in unmatched_users] # ignore users that are not in rocketchat
        invite_users = [user for user in desired_users if not user in current_users]
        kick_users = [user for user in current_users if not user in desired_users]
        
        print(f"> this action will invite the following users:\n> {invite_users}")
        print(f"> this action will kick the following users:\n> {kick_users}")
        
        if mapping.get("apply"):
            if mapping.get("private"):
                for user in invite_users:
                    rc.groups_invite(rc_channel_id, rc_users[user])
                for user in kick_users:
                    rc.groups_kick(rc_channel_id, rc_users[user])
            else:
                for user in invite_users:
                    rc.channels_invite(rc_channel_id, rc_users[user])
                for user in kick_users:
                    rc.channels_kick(rc_channel_id, rc_users[user])

def ldap_get_usernames(querystring:str) -> list:
    ldap_conn.search(LDAP_SEARCH_BASE, querystring, attributes=["sAMAccountName"])
    return [str(entry['sAMAccountName'].values[0]).lower() for entry in ldap_conn.entries]



if __name__ == "__main__":
    main()