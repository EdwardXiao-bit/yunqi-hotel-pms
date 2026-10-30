"""登录表单。"""
from __future__ import annotations

from django import forms


class LoginForm(forms.Form):
    username = forms.CharField(
        label="登录名",
        max_length=50,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "登录名", "autofocus": True, "autocomplete": "username"}
        ),
    )
    password = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "密码", "autocomplete": "current-password"}
        ),
    )

    def clean_username(self) -> str:
        return (self.cleaned_data["username"] or "").strip()
