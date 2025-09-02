from django import forms

class UserDeleteForm(forms.Form):
    confirm = forms.CharField(
        help_text='Type DELETE to confirm.',
        widget=forms.TextInput(attrs={'autocomplete': 'off'})
    )

    def clean_confirm(self):
        v = self.cleaned_data['confirm'].strip().upper()
        if v != "DELETE":
            raise forms.ValidationError("Type DELETE to confirm.")
        return v