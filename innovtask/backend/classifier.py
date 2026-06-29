"""
classifier.py - Deteccion del tipo de proceso por palabras clave.

Basado en como llegan las peticiones reales en INNOVTASK:
  - "generar el CA por areas" / "contextual assessment"  -> contextual_assessment
  - "ha sido certificada" / "el sello debe ir de..."      -> certificaciones
  - cualquier otra cosa                                    -> otro

No usa internet ni modelos pesados: solo reglas. Rapido y empaquetable.
La sugerencia se puede aceptar o cambiar a mano al crear la tarea.
"""
import re
import unicodedata

# Palabras/expresiones clave por tipo. Se comparan sobre texto normalizado
# (minusculas, sin tildes).
KEYWORDS = {
    "contextual_assessment": [
        r"\bca\b",                # "el CA", "generar el CA"
        "contextual assessment",
        "contextual",
        "por areas",
        "por area",
        "evaluacion de contexto",
        "assessment",
    ],
    "certificaciones": [
        "certificad",            # certificada, certificado, certificacion
        "certificacion",
        "sello",
        "vigencia",
        "renovacion del sello",
        "recertific",
    ],
}

LABELS = {
    "contextual_assessment": "Contextual Assessment",
    "certificaciones": "Certificaciones",
    "otro": "Otro",
}


def _normalize(text: str) -> str:
    text = (text or "").lower()
    # quitar tildes
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text


def detect_process_kind(text: str):
    """
    Devuelve (tipo, etiqueta, confianza_0a1).
    Cuenta cuantas claves de cada tipo aparecen; gana el de mas coincidencias.
    """
    norm = _normalize(text)
    scores = {}
    for kind, patterns in KEYWORDS.items():
        score = 0
        for p in patterns:
            if p.startswith("\\b") or p.endswith("\\b"):
                if re.search(p, norm):
                    score += 1
            elif p in norm:
                score += 1
        scores[kind] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "otro", LABELS["otro"], 0.0

    total = sum(scores.values()) or 1
    confidence = round(scores[best] / total, 2)
    return best, LABELS[best], confidence


if __name__ == "__main__":
    # Pruebas rapidas con los mensajes reales
    pruebas = [
        "Agradezco me colaboren generando el CA por Areas de la empresa Marcali S.A.S.",
        "Les confirmo que esta empresa ha sido certificada. El sello debe ir de Jun 2026 a Jun 2027.",
        "Necesito que revisen el informe trimestral del cliente.",
    ]
    for p in pruebas:
        print(detect_process_kind(p), "<-", p[:50])
