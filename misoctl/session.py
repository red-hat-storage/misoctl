import koji
from koji_cli.lib import activate_session
from misoctl.log import log as log


def get_session(profile):
    """
    Return an authenticated Koji session
    """
    # Return a cached session, if available.
    conf = koji.read_config(profile)
    hub = conf['server']
    session = koji.ClientSession(hub, {})
    # session.krb_login()
    activate_session(session, conf)
    assert session.logged_in
    userinfo = session.getLoggedInUser()
    username = userinfo['name']
    log.info('authenticated to %s as %s' % (hub, username))
    return session
