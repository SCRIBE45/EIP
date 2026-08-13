
import streamlit as st
import sqlite3
import random
import datetime
from pathlib import Path
import shutil
import os

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


# ============================================================
# BASE DE DATOS
# ============================================================

@st.cache_resource
def get_connection():
    # Copia la base de datos a un directorio temporal de escritura (/tmp) 
    # para evitar bloqueos de solo lectura en Streamlit Cloud
    temp_db_path = "/tmp/examen_temp.db"
    if not os.path.exists(temp_db_path) and DB_PATH.exists():
        shutil.copyfile(str(DB_PATH), temp_db_path)
    
    db_to_use = temp_db_path if os.path.exists(temp_db_path) else str(DB_PATH)
    conn = sqlite3.connect(db_to_use, check_same_thread=False)
    return conn


def setup_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(Preguntas)")
    columnas = [c[1] for c in cur.fetchall()]

    nuevas_columnas = {
        "ultima_vista": "TEXT",
        "veces_acertada": "INTEGER DEFAULT 0",
        "veces_fallada": "INTEGER DEFAULT 0",
        "intervalo": "INTEGER DEFAULT 0",
        "proxima_revision": "TEXT",
        "factor_facilidad": "REAL DEFAULT 2.5",
    }

    for col, tipo in nuevas_columnas.items():
        if col not in columnas:
            cur.execute(f"ALTER TABLE Preguntas ADD COLUMN {col} {tipo}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS RegistroDiario (
            fecha TEXT PRIMARY KEY,
            respondidas INTEGER DEFAULT 0,
            acertadas INTEGER DEFAULT 0,
            tiempo_segundos INTEGER DEFAULT 0,
            racha_maxima INTEGER DEFAULT 0
        )
    """)

    conn.commit()


setup_db()


# ============================================================
# FUNCIONES DE DATOS
# ============================================================

def get_questions(modo, tema):
    conn = get_connection()

    query = """
        SELECT id, enunciado, opcion_a, opcion_b, opcion_c, opcion_d,
               correcta, explicacion, tema, veces_acertada, veces_fallada,
               intervalo, factor_facilidad, proxima_revision
        FROM Preguntas
    """

    filtros = []
    parametros = []

    if tema != "Todos los temas":
        filtros.append("tema = ?")
        parametros.append(tema)

    if modo == "inteligente":
        hoy = datetime.date.today().isoformat()
        filtros.append("(proxima_revision IS NULL OR proxima_revision <= ?)")
        parametros.append(hoy)

    elif modo == "falladas":
        filtros.append("veces_fallada > 0")

    if filtros:
        query += " WHERE " + " AND ".join(filtros)

    if modo == "simulacro":
        query += " ORDER BY RANDOM() LIMIT 40"
    else:
        query += " ORDER BY RANDOM()"

    return conn.execute(query, parametros).fetchall()


def actualizar_registro_diario(acertada, tiempo_gastado=0, racha=0):
    conn = get_connection()
    cur = conn.cursor()
    hoy = datetime.date.today().isoformat()

    cur.execute(
        """SELECT respondidas, acertadas, tiempo_segundos, racha_maxima
           FROM RegistroDiario WHERE fecha=?""",
        (hoy,),
    )
    registro = cur.fetchone()

    if registro:
        resp, acert, tiempo, racha_max = registro

        cur.execute(
            """UPDATE RegistroDiario
               SET respondidas=?, acertadas=?, tiempo_segundos=?, racha_maxima=?
               WHERE fecha=?""",
            (
                resp + 1,
                acert + (1 if acertada else 0),
                tiempo + tiempo_gastado,
                max(racha_max, racha),
                hoy,
            ),
        )
    else:
        cur.execute(
            """INSERT INTO RegistroDiario
               (fecha, respondidas, acertadas, tiempo_segundos, racha_maxima)
               VALUES (?, ?, ?, ?, ?)""",
            (
                hoy,
                1,
                1 if acertada else 0,
                tiempo_gastado,
                racha,
            ),
        )

    conn.commit()


def actualizar_algoritmo(pregunta, es_correcta):
    conn = get_connection()

    (
        id_preg,
        _enunciado,
        _a,
        _b,
        _c,
        _d,
        _correcta,
        _explicacion,
        _tema,
        aciertos,
        fallos,
        intervalo,
        factor,
        _proxima,
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

    conn.execute(
        """UPDATE Preguntas
           SET veces_acertada=?, veces_fallada=?, intervalo=?,
               factor_facilidad=?, proxima_revision=?, ultima_vista=?
           WHERE id=?""",
        (
            aciertos,
            fallos,
            intervalo,
            factor,
            proxima,
            hoy.isoformat(),
            id_preg,
        ),
    )
    conn.commit()

    return aciertos, fallos, intervalo, factor


def get_today_stats():
    conn = get_connection()
    hoy = datetime.date.today().isoformat()

    return conn.execute(
        """SELECT respondidas, acertadas, tiempo_segundos, racha_maxima
           FROM RegistroDiario WHERE fecha=?""",
        (hoy,),
    ).fetchone()


def get_module_stats():
    conn = get_connection()
    resultado = []

    for tema in TEMAS_OFICIALES[1:]:
        total, fallos, aciertos = conn.execute(
            """SELECT COUNT(*), SUM(veces_fallada), SUM(veces_acertada)
               FROM Preguntas WHERE tema=?""",
            (tema,),
        ).fetchone()

        fallos = fallos or 0
        aciertos = aciertos or 0

        porc = (
            aciertos / (aciertos + fallos)
            if aciertos + fallos > 0
            else 0
        )

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
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# ESTILO (Solución para el recorte superior)
# ============================================================

st.markdown("""
<style>
    [data-testid="stHeader"] {
        background: transparent;
    }

    .block-container {
        max-width: 760px;
        padding-top: 0.5rem !important; /* Reduce el espacio superior */
        padding-bottom: 3rem;
        margin-top: -2rem !important;  /* Eleva la vista para que no se corte */
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
    }

    .tema {
        display: inline-block;
        background: #e8f2f8;
        color: #17608a;
        padding: 0.35rem 0.7rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
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
    st.markdown('<div class="titulo">📚 EIP Trainer</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitulo">Preparación para el European Investment Practitioner</div>',
        unsafe_allow_html=True,
    )

    reg = get_today_stats()

    if reg and reg[0]:
        respondidas, acertadas, tiempo, racha = reg
        porc = acertadas / respondidas * 100

        st.info(
            f"📝 {respondidas} preguntas   |   "
            f"🎯 {porc:.1f}% acierto   |   "
            f"⏱ {tiempo // 60} min   |   "
            f"🔥 Racha: {racha}"
        )
    else:
        st.info("📝 0 preguntas   |   🎯 0% acierto   |   ⏱ 0 min   |   🔥 0")

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

    modos = {
        "simulacro": "📝 Simulacro",
        "inteligente": "🧠 Repaso inteligente",
        "falladas": "🔄 Solo falladas",
        "libre": "🎲 Práctica libre",
    }

    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("🏠 Inicio"):
            st.session_state.pantalla = "dashboard"
            st.rerun()

    with col2:
        st.write(f"**{modos[st.session_state.modo]}**")

    st.progress((indice + 1) / total)

    st.caption(f"Pregunta {indice + 1} / {total}")

    tema_corto = p[8].split(". ", 1)[1] if ". " in p[8] else p[8]

    st.markdown(
        f'<div class="tema">{tema_corto}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="pregunta">{p[1]}</div>',
        unsafe_allow_html=True,
    )

    opciones = {
        "A": p[2],
        "B": p[3],
        "C": p[4],
        "D": p[5],
    }

    # Antes de responder
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
        correcta = p[6]
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

    correcta = p[6]
    es_correcta = seleccion == correcta

    if es_correcta:
        st.session_state.aciertos += 1
        st.session_state.racha += 1
    else:
        st.session_state.racha = 0

        if st.session_state.modo == "simulacro":
            st.session_state.errores_simulacro[p[8]] += 1

    actualizar_algoritmo(p, es_correcta)

    if st.session_state.modo != "simulacro":
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

        # Mantiene el comportamiento general de la app original.
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
    st.title("📊 Estadísticas")

    if st.button("🏠 Inicio"):
        st.session_state.pantalla = "dashboard"
        st.rerun()

    st.divider()

    for tema, total, porc in get_module_stats():
        nombre = tema.split(". ", 1)[1] if ". " in tema else tema

        st.write(f"**{nombre}**")
        st.progress(porc)
        st.caption(
            f"{porc * 100:.0f}% — {total} preguntas"
        )

        st.divider()


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

