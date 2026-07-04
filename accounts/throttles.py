from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    scope = "auth_login"

    def get_cache_key(self, request, view):
        if request.method != "POST":
            return None

        identifier = (
            request.data.get("identifier")
            or request.data.get("username")
            or request.data.get("email")
            or request.data.get("mobile")
            or "missing"
        )

        identifier = str(identifier).strip().lower()
        client_ip = self.get_ident(request)

        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{client_ip}:{identifier}",
        }