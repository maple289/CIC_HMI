"""Build-time policy; protected operator releases cannot enable test transports."""
PRODUCTION = False


def simulation_allowed(authorized=False):
    return bool(authorized and not PRODUCTION)
