from crispy_forms.layout import HTML

django_msgs = HTML(
    '{% if messages %}'
    '{% for message in messages %}<div class="alert alert-{{message.tags}}">{{ message|safe }}</div> {% endfor %}'
    '{% endif %}')