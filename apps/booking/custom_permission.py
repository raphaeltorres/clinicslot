from rest_framework.permissions import BasePermission


class ClinicPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            return False

        if user.is_superuser:
            return True
        
        if user.groups.filter(name="Tenant Admin").exists():
            return True

        permission_map = getattr(view, "permission_map", {})
        required_perm = permission_map.get(view.action)

        if not required_perm:
            return False

        if isinstance(required_perm, str):
            required_perm = [required_perm]

        return all(user.has_perm(perm) for perm in required_perm)
    
class SuperUserPerimission(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser

    