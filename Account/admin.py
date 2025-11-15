from django.contrib import admin
from .models import CustomUser, VerificationToken, PasswordResetToken

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'is_verified', 'is_staff', 'created_at')
    search_fields = ('email', 'first_name', 'last_name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(VerificationToken)
class VerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token')
    readonly_fields = ('created_at',)

@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token')
    readonly_fields = ('created_at',)
