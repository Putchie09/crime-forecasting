"""
Custom template tags and filters for the forecasting app.
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Permite acceder a dict[key] en plantillas: {{ mydict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(str(key), '')
    return ''


@register.filter(name='abs_value')
def abs_value(value):
    """Devuelve el valor absoluto de un número."""
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return value


@register.filter(name='percentage')
def percentage(value, decimals=1):
    """Formatea un flotante como una cadena porcentual."""
    try:
        return f"{float(value):.{int(decimals)}f}%"
    except (TypeError, ValueError):
        return str(value)


@register.filter(name='titlecase_es')
def titlecase_es(value):
    """
    Title-case a string but keep Spanish articles lowercase.
    e.g.  'ASALTO A MANO ARMADA' → 'Asalto a Mano Armada'
    """
    if not isinstance(value, str):
        return value
    lower_words = {'a', 'al', 'de', 'del', 'en', 'y', 'o', 'e', 'la', 'las', 'los', 'el'}
    words = value.lower().split()
    result = []
    for i, word in enumerate(words):
        if i == 0 or word not in lower_words:
            result.append(word.capitalize())
        else:
            result.append(word)
    return ' '.join(result)


@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """
    Construye una cadena de consulta preservando los parámetros GET actuales y sobrescribiendo con kwargs.
    Uso: {% query_string page=2 %} → ?q=foo&canton=BAR&page=2
    """
    request = context.get('request')
    if request is None:
        params = {}
    else:
        params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return '?' + params.urlencode() if params else ''


@register.filter(name='month_name_es')
def month_name_es(month_number):
    """Convierte un entero de mes en el nombre del mes en español."""
    names = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Setiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
    }
    try:
        return names.get(int(month_number), str(month_number))
    except (TypeError, ValueError):
        return str(month_number)


@register.inclusion_tag('partials/pagination.html', takes_context=True)
def pagination(context, page_obj, page_range):
    """Renderiza el parcial de control de paginación."""
    return {
        'page_obj': page_obj,
        'page_range': page_range,
        'request': context.get('request'),
        'filter_q': context.get('filter_q', ''),
        'filter_canton': context.get('filter_canton', ''),
        'filter_delito': context.get('filter_delito', ''),
        'filter_sexo': context.get('filter_sexo', ''),
        'filter_date_from': context.get('filter_date_from', ''),
        'filter_date_to': context.get('filter_date_to', ''),
    }
