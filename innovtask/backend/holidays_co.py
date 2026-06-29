"""
holidays_co.py - Festivos de Colombia calculados para CUALQUIER año.

No usa internet ni listas fijas: calcula todo con la fecha de Pascua
(algoritmo de Gauss/Butcher) y la Ley Emiliani (festivos que se trasladan
al lunes siguiente). Asi la app funciona en 2026, 2027 y cualquier año.
"""
import datetime


def _easter(year: int) -> datetime.date:
    """Domingo de Pascua (algoritmo de Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _next_monday(d: datetime.date) -> datetime.date:
    """Traslada al lunes siguiente (Ley Emiliani). Si ya es lunes, lo deja."""
    while d.weekday() != 0:  # 0 = lunes
        d += datetime.timedelta(days=1)
    return d


def holidays_for_year(year: int) -> dict:
    """
    Devuelve {fecha_iso: nombre} con todos los festivos de Colombia del año.
    """
    easter = _easter(year)
    h = {}

    def add(date, name):
        h[date.isoformat()] = name

    # Fijos (no se trasladan)
    add(datetime.date(year, 1, 1), "Año Nuevo")
    add(datetime.date(year, 5, 1), "Día del Trabajo")
    add(datetime.date(year, 7, 20), "Día de la Independencia")
    add(datetime.date(year, 8, 7), "Batalla de Boyacá")
    add(datetime.date(year, 12, 8), "Inmaculada Concepción")
    add(datetime.date(year, 12, 25), "Navidad")

    # Trasladables a lunes (Ley Emiliani)
    add(_next_monday(datetime.date(year, 1, 6)), "Reyes Magos")
    add(_next_monday(datetime.date(year, 3, 19)), "San José")
    add(_next_monday(datetime.date(year, 6, 29)), "San Pedro y San Pablo")
    add(_next_monday(datetime.date(year, 8, 15)), "Asunción de la Virgen")
    add(_next_monday(datetime.date(year, 10, 12)), "Día de la Raza")
    add(_next_monday(datetime.date(year, 11, 1)), "Todos los Santos")
    add(_next_monday(datetime.date(year, 11, 11)), "Independencia de Cartagena")

    # Basados en Pascua
    add(easter + datetime.timedelta(days=-3), "Jueves Santo")
    add(easter + datetime.timedelta(days=-2), "Viernes Santo")
    add(_next_monday(easter + datetime.timedelta(days=43)), "Ascensión del Señor")
    add(_next_monday(easter + datetime.timedelta(days=64)), "Corpus Christi")
    add(_next_monday(easter + datetime.timedelta(days=71)), "Sagrado Corazón")

    return h


if __name__ == "__main__":
    for f, n in sorted(holidays_for_year(2026).items()):
        print(f, n)
