from django import forms

from .models import Response


class ResponseForm(forms.ModelForm):
    score = forms.TypedChoiceField(
        choices=[(number, str(number)) for number in range(1, 6)],
        coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Response
        fields = ("score", "comment")
        widgets = {
            "comment": forms.Textarea(attrs={"placeholder": "Share context, a win, or something worth watching…"}),
        }
