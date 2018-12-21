import koji
from koji_cli.lib import activate_session
from misoctl.log import log as log


def get_session(profile):
    """
    Return an authenticated Koji session
    """
    # Return a cached session, if available.
    mykoji = koji.get_profile_module(profile)
    opts = mykoji.grab_session_options(mykoji.config)
    session = koji.ClientSession(mykoji.config.server, opts)
    # Log in ("activate") this sesssion:
    # Note: this can raise SystemExit if there is a problem, eg with Kerberos:
    activate_session(session, mykoji.config)
    assert session.logged_in
    userinfo = session.getLoggedInUser()
    username = userinfo['name']
    log.info('authenticated to %s as %s' % (mykoji.config.server, username))
    return session
