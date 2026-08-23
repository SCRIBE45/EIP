import streamlit as st
import sqlite3
import random
import datetime
import json
import base64
import requests
from pathlib import Path
import streamlit.components.v1 as components

# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="EIP Trainer",
    page_icon="📚",
    layout="centered",
)

TEMAS_OFICIALES = [
    "Todos los temas",
    "Módulo 1. Instrumentos y Mercados Financieros",
    "Módulo 2. Fondos y Sociedades de Inversión Mobiliaria",
    "Módulo 3. Gestión de carteras",
    "Módulo 4. Seguros",
    "Módulo 5. Pensiones y planificación de la jubilación",
    "Módulo 6. Fiscalidad",
    "Módulo 7. Cumplimiento normativo y regulador",
    "Módulo 8. Asesoramiento y planificación financiera",
]

DB_PATH = Path(__file__).parent / "examen.db"
FILE_PROGRESS_PATH = "progreso.json"

# ============================================================
# PERSISTENCIA VÍA GITHUB API
# ============================================================

@st.cache_resource
def get_db_connection():
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)

def get_github_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

def cargar_datos_remotos():
    repo = st.secrets.get("GITHUB_REPO", "")
    url = f"https://api.github.com/repos/{repo}/contents/{FILE_PROGRESS_PATH}"
    headers = get_github_headers()
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            st.session_state["_github_sha"] = data["sha"]
            return json.loads(content)
    except Exception:
        pass
        
    return {"progreso": {}, "registro_diario": {}}

def guardar_datos_remotos(datos):
    repo = st.secrets.get("GITHUB_REPO", "")
    if not repo:
        return
    url = f"https://api.github.com/repos/{repo}/contents/{FILE_PROGRESS_PATH}"
    headers = get_github_headers()
    
    content_str = json.dumps(datos, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": "Actualizar progreso de estudio [Skip CI]",
        "content": content_b64
    }
    
    if "_github_sha" in st.session_state and st.session_state["_github_sha"]:
        payload["sha"] = st.session_state["_github_sha"]
        
    try:
        res = requests.put(url, headers=headers, json=payload)
        if res.status_code in [200, 201]:
            st.session_state["_github_sha"] = res.json()["content"]["sha"]
    except Exception:
        pass

if "datos_usuario" not in st.session_state:
    st.session_state.datos_usuario = cargar_datos_remotos()

def guardar_progreso_pregunta(id_preg, aciertos, fallos, intervalo, factor, proxima, hoy_str):
    datos = st.session_state.datos_usuario
    datos["progreso"][str(id_preg)] = {
        "veces_acertada": aciertos,
        "veces_fallada": fallos,
        "intervalo": intervalo,
        "factor_facilidad": factor,
        "proxima_revision": proxima,
        "ultima_vista": hoy_str
    }
    guardar_datos_remotos(datos)

def actualizar_registro_diario(acertada, tiempo_gastado=0, racha=0):
    datos = st.session_state.datos_usuario
    hoy = datetime.date.today().isoformat()
    
    reg = datos["registro_diario"].get(hoy, {
        "respondidas": 0,
        "acertadas": 0,
        "tiempo_segundos": 0,
        "racha_maxima": 0
    })
    
    reg["respondidas"] += 1
    if acertada:
        reg["acertadas"] += 1
    reg["tiempo_segundos"] += int(tiempo_gastado)
    reg["racha_maxima"] = max(reg.get("racha_maxima", 0), int(racha))
    
    datos["registro_diario"][hoy] = reg
    guardar_datos_remotos(datos)

# ============================================================
# FUNCIONES DE DATOS
# ============================================================

def get_questions(modo, tema):
    conn = get_db_connection()
    query = """
        SELECT id, enunciado, opcion_a, opcion_b, opcion_c, opcion_d,
               correcta, explicacion, tema
        FROM Preguntas
    """
    parametros = []
    if tema != "Todos los temas":
        query += " WHERE tema = ?"
        parametros.append(tema)

    filas = conn.execute(query, parametros).fetchall()
    prog_dict = st.session_state.datos_usuario.get("progreso", {})
    
    preguntas_completas = []
    hoy = datetime.date.today().isoformat()

    for p in filas:
        p_id = str(p[0])
        prog = prog_dict.get(p_id, {})
        
        aciertos = prog.get("veces_acertada", 0)
        fallos = prog.get("veces_fallada", 0)
        intervalo = prog.get("intervalo", 0)
        factor = prog.get("factor_facilidad", 2.5)
        proxima = prog.get("proxima_revision", None)

        if modo == "inteligente":
            if proxima and proxima > hoy:
                continue
        elif modo == "falladas":
            if fallos == 0:
                continue

        preguntas_completas.append((
            p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8],
            aciertos, fallos, intervalo, factor, proxima
        ))

    if modo == "simulacro":
        random.shuffle(preguntas_completas)
        return preguntas_completas[:40]
    else:
        random.shuffle(preguntas_completas)
        return preguntas_completas

def actualizar_algoritmo(pregunta, es_correcta):
    (
        id_preg, _enunciado, _a, _b, _c, _d, _correcta, _explicacion,
        _tema, aciertos, fallos, intervalo, factor, _proxima
    ) = pregunta

    aciertos = aciertos or 0
    fallos = fallos or 0
    intervalo = intervalo or 0
    factor = factor or 2.5

    if es_correcta:
        aciertos += 1
        if aciertos == 1:
            intervalo = 1
        elif aciertos == 2:
            intervalo = 3
        else:
            intervalo = round(intervalo * factor)
        factor = min(3.0, factor + 0.1)
    else:
        aciertos = 0
        fallos += 1
        intervalo = 0
        factor = max(1.3, factor - 0.2)

    hoy = datetime.date.today()
    proxima = (hoy + datetime.timedelta(days=intervalo)).isoformat()

    guardar_progreso_pregunta(
        id_preg, aciertos, fallos, intervalo, factor, proxima, hoy.isoformat()
    )

    return aciertos, fallos, intervalo, factor

def get_today_stats():
    hoy = datetime.date.today().isoformat()
    reg = st.session_state.datos_usuario.get("registro_diario", {}).get(hoy)
    if reg:
        return (
            reg.get("respondidas", 0),
            reg.get("acertadas", 0),
            reg.get("tiempo_segundos", 0),
            reg.get("racha_maxima", 0)
        )
    return None

def get_module_stats():
    conn = get_db_connection()
    prog_dict = st.session_state.datos_usuario.get("progreso", {})
    resultado = []

    for tema in TEMAS_OFICIALES[1:]:
        total = conn.execute(
            "SELECT COUNT(*) FROM Preguntas WHERE tema=?", (tema,)
        ).fetchone()[0]

        ids_modulo = [
            str(row[0]) for row in conn.execute(
                "SELECT id FROM Preguntas WHERE tema=?", (tema,)
            ).fetchall()
        ]

        aciertos = sum(prog_dict.get(pid, {}).get("veces_acertada", 0) for pid in ids_modulo)
        fallos = sum(prog_dict.get(pid, {}).get("veces_fallada", 0) for pid in ids_modulo)

        porc = aciertos / (aciertos + fallos) if (aciertos + fallos) > 0 else 0
        resultado.append((tema, total, porc))

    return resultado

# ============================================================
# ESTADO DE LA SESIÓN
# ============================================================

defaults = {
    "pantalla": "dashboard",
    "modo": None,
    "tema": "Todos los temas",
    "preguntas": [],
    "indice": 0,
    "aciertos": 0,
    "racha": 0,
    "respondida": False,
    "seleccion": None,
    "resultado": None,
    "explicacion": "",
    "errores_simulacro": {},
    "inicio_simulacro": None,
    "opciones_actuales": None,
    "correcta_actual": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================
# ESTILO
# ============================================================

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .block-container {
        max-width: 760px;
        padding-top: 0.5rem !important;
        padding-bottom: 3rem;
        margin-top: -2rem !important;
    }

    div[data-testid="stButton"] button {
        white-space: normal !important;
        height: auto !important;
        min-height: 3rem;
        padding: 0.75rem 1rem !important;
        text-align: left !important;
    }
    
    div[data-testid="stButton"] button p {
        text-align: left !important;
        font-size: 1rem;
    }

    .titulo {
        font-size: 2.2rem;
        font-weight: 700;
        text-align: center;
    }

    .subtitulo {
        text-align: center;
        color: #777;
        margin-bottom: 1.5rem;
    }

    .pregunta {
        font-size: 1.35rem;
        font-weight: 650;
        line-height: 1.45;
        margin: 1rem 0 1.5rem 0;
        text-align: left;
    }

    .correcto {
        padding: 1rem;
        border-radius: 10px;
        background: #e8f7ee;
        border: 1px solid #8bd0a5;
        color: #146c37;
    }

    .incorrecto {
        padding: 1rem;
        border-radius: 10px;
        background: #fdecec;
        border: 1px solid #e0a0a0;
        color: #8b2020;
    }

    .explicacion {
        padding: 1rem;
        border-radius: 10px;
        background: #eaf5fa;
        border: 1px solid #abd5e5;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# DASHBOARD
# ============================================================

def dashboard():
    st.markdown('<div class="titulo">📚 Preparador del EIP</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitulo">Preparación para el European Investment Practitioner</div>',
        unsafe_allow_html=True,
    )

    reg = get_today_stats()

    if reg and reg[0]:
        respondidas, acertadas, tiempo, racha = reg
        porc = acertadas / respondidas * 100

        st.success("¡Buen trabajo! Aquí tienes tu resumen diario: 🚀")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preguntas 📝", respondidas)
        c2.metric("Aciertos 🎯", f"{porc:.0f}%")
        c3.metric("Tiempo ⏱", f"{tiempo // 60} min")
        c4.metric("Racha 🔥", racha)
    else:
        st.info("¡Vamos a por la sesión de hoy! 📝")

    st.selectbox(
        "Seleccionar módulo",
        TEMAS_OFICIALES,
        key="tema",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📝 Simulacro\n40 preguntas", use_container_width=True):
            iniciar_sesion("simulacro")

        if st.button("🔄 Solo falladas", use_container_width=True):
            iniciar_sesion("falladas")

    with col2:
        if st.button("🧠 Repaso inteligente", use_container_width=True):
            iniciar_sesion("inteligente")

        if st.button("🎲 Práctica libre", use_container_width=True):
            iniciar_sesion("libre")

    st.divider()

    if st.button("📊 Estadísticas", use_container_width=True):
        st.session_state.pantalla = "stats"
        st.rerun()

# ============================================================
# SESIÓN
# ============================================================

def iniciar_sesion(modo):
    preguntas = get_questions(modo, st.session_state.tema)

    st.session_state.modo = modo
    st.session_state.preguntas = preguntas
    st.session_state.indice = 0
    st.session_state.aciertos = 0
    st.session_state.racha = 0
    st.session_state.respondida = False
    st.session_state.seleccion = None
    st.session_state.resultado = None
    st.session_state.explicacion = ""
    st.session_state.opciones_actuales = None
    st.session_state.correcta_actual = None
    st.session_state.errores_simulacro = {
        t: 0 for t in TEMAS_OFICIALES[1:]
    }
    st.session_state.inicio_simulacro = (
        datetime.datetime.now() if modo == "simulacro" else None
    )

    st.session_state.pantalla = "session"
    st.rerun()

def session():
    preguntas = st.session_state.preguntas
    indice = st.session_state.indice

    if not preguntas:
        st.warning("No hay preguntas disponibles para este modo/filtro.")
        if st.button("🏠 Volver al inicio"):
            st.session_state.pantalla = "dashboard"
            st.rerun()
        return

    p = preguntas[indice]
    total = len(preguntas)
    
    if st.session_state.opciones_actuales is None:
        textos_originales = {"A": p[2], "B": p[3], "C": p[4], "D": p[5]}
        texto_correcto = textos_originales[p[6]]
        
        lista_textos = list(textos_originales.values())
        random.shuffle(lista_textos)
        
        st.session_state.opciones_actuales = {
            "A": lista_textos[0],
            "B": lista_textos[1],
            "C": lista_textos[2],
            "D": lista_textos[3],
        }
        
        for letra, texto in st.session_state.opciones_actuales.items():
            if texto == texto_correcto:
                st.session_state.correcta_actual = letra
                break

    opciones = st.session_state.opciones_actuales
    correcta = st.session_state.correcta_actual

    modos = {
        "simulacro": "📝 Simulacro",
        "inteligente": "🧠 Repaso inteligente",
        "falladas": "🔄 Solo falladas",
        "libre": "🎲 Práctica libre",
    }

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("🏠 Inicio"):
            st.session_state.pantalla = "dashboard"
            st.rerun()

    with col2:
        st.write(f"**{modos[st.session_state.modo]}**")
        
    with col3:
        if st.session_state.modo == "simulacro" and st.session_state.inicio_simulacro:
            limite = st.session_state.inicio_simulacro + datetime.timedelta(hours=1)
            restante = int((limite - datetime.datetime.now()).total_seconds())
            
            if restante <= 0:
                finalizar_sesion()
                st.rerun()
            
            html_reloj = f"""
            <div id="reloj" style="font-family: sans-serif; font-size: 1.2rem; font-weight: bold; color: #C63B3B; text-align: right;"></div>
            <script>
                var tiempo = {restante};
                var timer = setInterval(function() {{
                    if (tiempo <= 0) {{
                        clearInterval(timer);
                        document.getElementById('reloj').innerHTML = "⏱ 00:00";
                    }} else {{
                        var m = Math.floor(tiempo / 60);
                        var s = Math.floor(tiempo % 60);
                        document.getElementById('reloj').innerHTML = "⏱ " + (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
                        tiempo--;
                    }}
                }}, 1000);
            </script>
            """
            components.html(html_reloj, height=35)

    st.progress((indice + 1) / total)
    st.caption(f"Pregunta {indice + 1} / {total}")

    st.markdown(f'<div class="pregunta">{p[1]}</div>', unsafe_allow_html=True)

    if not st.session_state.respondida:
        for letra, texto in opciones.items():
            if st.button(
                f"{letra}) {texto}",
                key=f"opcion_{indice}_{letra}",
                use_container_width=True,
            ):
                responder(letra)
                st.rerun()
    else:
        seleccion = st.session_state.seleccion

        for letra, texto in opciones.items():
            if letra == correcta:
                st.success(f"✅ {letra}) {texto}")
            elif letra == seleccion:
                st.error(f"❌ {letra}) {texto}")
            else:
                st.button(
                    f"{letra}) {texto}",
                    key=f"disabled_{indice}_{letra}",
                    disabled=True,
                    use_container_width=True,
                )

        if st.session_state.resultado:
            st.markdown(
                '<div class="correcto">✅ ¡Correcto!</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="incorrecto">❌ Incorrecto. '
                f'La respuesta correcta era la {correcta}.</div>',
                unsafe_allow_html=True,
            )

        if st.session_state.explicacion:
            st.markdown(
                f'<div class="explicacion"><b>💡 Explicación</b><br><br>'
                f'{st.session_state.explicacion}</div>',
                unsafe_allow_html=True,
            )

        st.write("")

        if st.button("Siguiente ➜", type="primary", use_container_width=True):
            siguiente_pregunta()
            st.rerun()

def responder(seleccion):
    p = st.session_state.preguntas[st.session_state.indice]

    correcta = st.session_state.correcta_actual
    es_correcta = seleccion == correcta

    if es_correcta:
        st.session_state.aciertos += 1
        st.session_state.racha += 1
    else:
        st.session_state.racha = 0
        if st.session_state.modo == "simulacro":
            st.session_state.errores_simulacro[p[8]] += 1

    actualizar_algoritmo(p, es_correcta)

    if st.session_state.modo == "simulacro":
        siguiente_pregunta()
    else:
        actualizar_registro_diario(
            es_correcta,
            tiempo_gastado=15,
            racha=st.session_state.racha,
        )
        st.session_state.seleccion = seleccion
        st.session_state.resultado = es_correcta
        st.session_state.explicacion = p[7] or ""
        st.session_state.respondida = True

def siguiente_pregunta():
    preguntas = st.session_state.preguntas
    indice = st.session_state.indice

    if indice + 1 < len(preguntas):
        pendientes = preguntas[indice + 1:]
        racha = st.session_state.racha

        if racha >= 5:
            pendientes.sort(key=lambda x: (x[12], -(x[10] or 0)))
        elif racha == 0:
            pendientes.sort(key=lambda x: (-(x[12] or 0), x[9] or 0))
        else:
            random.shuffle(pendientes)

        st.session_state.preguntas[indice + 1:] = pendientes

    st.session_state.indice += 1
    st.session_state.respondida = False
    st.session_state.seleccion = None
    st.session_state.resultado = None
    st.session_state.explicacion = ""
    st.session_state.opciones_actuales = None
    st.session_state.correcta_actual = None

    if st.session_state.indice >= len(st.session_state.preguntas):
        finalizar_sesion()

def finalizar_sesion():
    total = len(st.session_state.preguntas)
    aciertos = st.session_state.aciertos
    nota = aciertos / total * 10 if total else 0

    if st.session_state.modo == "simulacro":
        inicio = st.session_state.inicio_simulacro
        tiempo = (
            int((datetime.datetime.now() - inicio).total_seconds())
            if inicio else 0
        )

        actualizar_registro_diario(
            acertada=False,
            tiempo_gastado=tiempo,
            racha=st.session_state.racha,
        )

    st.session_state.nota = nota
    st.session_state.pantalla = "results"

# ============================================================
# RESULTADOS
# ============================================================

def results():
    total = len(st.session_state.preguntas)

    st.title("🏆 Resultados")

    st.metric(
        "Aciertos",
        f"{st.session_state.aciertos} / {total}",
    )

    st.metric(
        "Nota equivalente",
        f"{st.session_state.nota:.1f} / 10",
    )

    if st.session_state.modo == "simulacro":
        errores = st.session_state.errores_simulacro
        errores = {k: v for k, v in errores.items() if v}

        if errores:
            st.subheader("📉 Errores por módulo")
            for tema, cantidad in errores.items():
                st.write(f"**{tema}:** {cantidad} fallos")

    if st.button("🏠 Volver al inicio", use_container_width=True):
        st.session_state.pantalla = "dashboard"
        st.rerun()

# ============================================================
# ESTADÍSTICAS
# ============================================================

def stats():
    st.title("📊 Tu progreso de estudio")

    if st.button("🏠 Volver al inicio"):
        st.session_state.pantalla = "dashboard"
        st.rerun()

    st.write("¡Aquí tienes el resumen de cómo vas! Cada error es una oportunidad para aprender. 💪")
    st.divider()

    for tema, total, porc in get_module_stats():
        nombre = tema.split(". ", 1)[1] if ". " in tema else tema
        
        if porc >= 0.8:
            emoji = "🌟"
        elif porc >= 0.5:
            emoji = "👍"
        else:
            emoji = "💪"

        st.write(f"**{nombre}** {emoji}")
        st.progress(porc)
        st.caption(f"Has dominado el {porc * 100:.0f}% de este módulo ({total} preguntas totales).")
        st.write("")

# ============================================================
# ROUTER
# ============================================================

if st.session_state.pantalla == "dashboard":
    dashboard()
elif st.session_state.pantalla == "session":
    session()
elif st.session_state.pantalla == "results":
    results()
elif st.session_state.pantalla == "stats":
    stats()
