def premium_status(request):
    if request.user.is_authenticated:
        try:
            return {"user_is_premium": request.user.userprofile.is_premium_active()}
        except Exception:
            return {"user_is_premium": False}
    return {"user_is_premium": False}
