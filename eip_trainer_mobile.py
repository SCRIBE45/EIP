import streamlit as st
import sqlite3
import random
import datetime
from pathlib import Path
import shutil
import os
import pandas as pd
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


# ============================================================
# BASE DE DATOS
# ============================================================

@st.cache_resource
def get_connection():
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


def actualizar_registro_sesion(respondidas, acertadas, tiempo_segundos=0, racha=0):
    conn = get_connection(); cur = conn.cursor(); hoy = datetime.date.today().isoformat()
    cur.execute("SELECT respondidas, acertadas, tiempo_segundos, racha_maxima FROM RegistroDiario WHERE fecha=?", (hoy,))
    r = cur.fetchone()
    if r:
        resp, acert, tiempo, racha_max = r
        cur.execute("UPDATE RegistroDiario SET respondidas=?, acertadas=?, tiempo_segundos=?, racha_maxima=? WHERE fecha=?", (resp+respondidas, acert+acertadas, tiempo+tiempo_segundos, max(racha_max, racha), hoy))
    else:
        cur.execute("INSERT INTO RegistroDiario (fecha, respondidas, acertadas, tiempo_segundos, racha_maxima) VALUES (?, ?, ?, ?, ?)", (hoy, respondidas, acertadas, tiempo_segundos, racha))
    conn.commit()

def get_history_stats(dias=30):
    conn=get_connection(); hoy=datetime.date.today(); inicio=hoy-datetime.timedelta(days=dias-1)
    rows=conn.execute("SELECT fecha, respondidas, acertadas, tiempo_segundos, racha_maxima FROM RegistroDiario WHERE fecha>=? ORDER BY fecha", (inicio.isoformat(),)).fetchall()
    by_date={r[0]:r for r in rows}; data=[]
    for i in range(dias):
        f=inicio+datetime.timedelta(days=i); r=by_date.get(f.isoformat()); resp=r[1] if r else 0; ac=r[2] if r else 0
        data.append({'Fecha':f.strftime('%d/%m'),'Preguntas':resp,'Aciertos':ac,'Precisión':ac/resp*100 if resp else 0,'Tiempo (min)':(r[3] if r else 0)/60,'Racha':r[4] if r else 0})
    return pd.DataFrame(data)

def get_global_stats():
    conn=get_connection(); total=conn.execute('SELECT COUNT(*) FROM Preguntas').fetchone()[0] or 0
    ac,fall,vistas,pend=conn.execute("""SELECT COALESCE(SUM(veces_acertada),0),COALESCE(SUM(veces_fallada),0),COALESCE(SUM(CASE WHEN veces_acertada>0 OR veces_fallada>0 THEN 1 ELSE 0 END),0),COALESCE(SUM(CASE WHEN proxima_revision IS NOT NULL AND proxima_revision<=? THEN 1 ELSE 0 END),0) FROM Preguntas""",(datetime.date.today().isoformat(),)).fetchone()
    domin=conn.execute("SELECT COUNT(*) FROM Preguntas WHERE veces_acertada>=3 AND veces_acertada>veces_fallada AND factor_facilidad>=2.5").fetchone()[0] or 0
    prob=conn.execute("SELECT COUNT(*) FROM Preguntas WHERE veces_fallada>=2 AND veces_fallada>=veces_acertada").fetchone()[0] or 0
    return {'total':total,'aciertos':ac,'fallos':fall,'intentos':ac+fall,'vistas':vistas,'precision':ac/(ac+fall) if ac+fall else 0,'dominadas':domin,'pendientes':pend,'problematicas':prob}

def get_module_stats():
    conn=get_connection(); result=[]
    for tema in TEMAS_OFICIALES[1:]:
        total=conn.execute('SELECT COUNT(*) FROM Preguntas WHERE tema=?',(tema,)).fetchone()[0] or 0
        ac,fall,vistas,domin=conn.execute("""SELECT COALESCE(SUM(veces_acertada),0),COALESCE(SUM(veces_fallada),0),COALESCE(SUM(CASE WHEN veces_acertada>0 OR veces_fallada>0 THEN 1 ELSE 0 END),0),COALESCE(SUM(CASE WHEN veces_acertada>=3 AND veces_acertada>veces_fallada AND factor_facilidad>=2.5 THEN 1 ELSE 0 END),0) FROM Preguntas WHERE tema=?""",(tema,)).fetchone()
        precision=ac/(ac+fall) if ac+fall else 0; cobertura=vistas/total if total else 0; dominio=domin/total if total else 0
        if cobertura<.20: nivel,emoji='No trabajado','⚪'
        elif precision<.60: nivel,emoji='Débil','🔴'
        elif precision<.80: nivel,emoji='En progreso','🟡'
        elif dominio>=.70 and precision>=.90: nivel,emoji='Dominado','⭐'
        else: nivel,emoji='Buen nivel','🟢'
        result.append({'tema':tema,'nombre':tema.split('. ',1)[1] if '. ' in tema else tema,'total':total,'vistas':vistas,'cobertura':cobertura,'aciertos':ac,'fallos':fall,'precision':precision,'dominadas':domin,'dominio':dominio,'nivel':nivel,'emoji':emoji})
    return result

def get_weak_questions(limit=8):
    conn=get_connection()
    return conn.execute("""SELECT enunciado,tema,veces_acertada,veces_fallada,factor_facilidad FROM Preguntas WHERE veces_fallada>0 ORDER BY veces_fallada DESC, CASE WHEN (veces_acertada+veces_fallada)>0 THEN CAST(veces_fallada AS REAL)/(veces_acertada+veces_fallada) ELSE 0 END DESC LIMIT ?""",(limit,)).fetchall()

def get_today_stats():
    conn = get_connection()
    hoy = datetime.date.today().isoformat()

    return conn.execute(
        """SELECT respondidas, acertadas, tiempo_segundos, racha_maxima
           FROM RegistroDiario WHERE fecha=?""",
        (hoy,),
    ).fetchone()


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
    "opciones_actuales": None,  # Añadido para mezclar respuestas
    "correcta_actual": None,    # Añadido para identificar la nueva letra correcta
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# ESTILO 
# ============================================================

st.markdown("""
<style>
    /* Ocultar elementos predeterminados de Streamlit que cortan la pantalla por arriba */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .block-container {
        max-width: 760px;
        padding-top: 0.5rem !important;
        padding-bottom: 3rem;
        margin-top: -2rem !important;
    }

    /* FORZAR MULTILÍNEA EN BOTONES PARA EVITAR QUE SE CORTEN LOS TEXTOS */
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

    .metric-card { padding: 0.8rem; border-radius: 12px; border: 1px solid rgba(128,128,128,.18); background: rgba(128,128,128,.05); }
    div[data-testid="stMetric"] { border: 1px solid rgba(128,128,128,.15); padding: .65rem; border-radius: 12px; background: rgba(128,128,128,.035); }
    div[data-testid="stTabs"] button { font-weight: 600; }

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

    stats = get_global_stats()
    today = get_today_stats()

    # Resumen compacto del día
    if today and today[0]:
        respondidas, acertadas, tiempo, racha = today
        porc = acertadas / respondidas * 100 if respondidas else 0
        st.markdown("### 📅 Hoy")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preguntas hoy", respondidas)
        c2.metric("Acierto", f"{porc:.0f}%")
        c3.metric("Tiempo", f"{tiempo // 60} min")
        c4.metric("Racha", f"🔥 {racha}")
    else:
        st.info("Todavía no has respondido preguntas hoy. ¡Vamos a empezar!")

    st.divider()

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

    # Acceso a estadísticas, separado del dashboard
    st.markdown("### 📊 Seguimiento")
    st.caption(
        f"{stats['vistas']} de {stats['total']} preguntas vistas · "
        f"{stats['precision'] * 100:.0f}% de precisión · "
        f"{stats['dominadas']} preguntas dominadas"
    )

    if st.button("📊 Ver estadísticas completas", use_container_width=True, type="primary"):
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
    
    # === Lógica para mezclar opciones solo una vez por pregunta ===
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
        
        # Encontrar cuál es la nueva letra correcta
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
            # Calcular tiempo restante en backend
            limite = st.session_state.inicio_simulacro + datetime.timedelta(hours=1)
            restante = int((limite - datetime.datetime.now()).total_seconds())
            
            # Si el tiempo se ha acabado, forzamos el fin
            if restante <= 0:
                finalizar_sesion()
                st.rerun()
            
            # Reloj visual en JavaScript
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
        # Flujo ininterrumpido: pasamos a la siguiente pregunta directamente
        siguiente_pregunta()
    else:
        # Modo estudio: mostramos corrección y guardamos el registro diario
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

        actualizar_registro_sesion(
            respondidas=total,
            acertadas=aciertos,
            tiempo_segundos=tiempo,
            racha=st.session_state.racha,
        )

    st.session_state.nota = nota
    st.session_state.pantalla = "results"


# ============================================================
# RESULTADOS
# ============================================================

def results():
    total=len(st.session_state.preguntas); aciertos=st.session_state.aciertos; nota=st.session_state.nota; errores={k:v for k,v in st.session_state.errores_simulacro.items() if v}
    st.markdown('<div class="titulo">🏆 Sesión terminada</div>',unsafe_allow_html=True); st.markdown('<div class="subtitulo">Resumen de tu rendimiento</div>',unsafe_allow_html=True)
    c1,c2,c3=st.columns(3); c1.metric("Aciertos",f"{aciertos} / {total}"); c2.metric("Precisión",f"{aciertos/total*100:.0f}%" if total else "0%"); c3.metric("Nota equivalente",f"{nota:.1f} / 10"); st.progress(aciertos/total if total else 0)
    if nota>=8: st.success("🌟 Muy buen resultado. Mantén el ritmo.")
    elif nota>=6: st.info("👍 Buen resultado, pero todavía hay margen de mejora.")
    else: st.warning("💪 Esta sesión señala áreas que conviene reforzar.")
    if st.session_state.modo=="simulacro" and errores:
        st.markdown("### 📉 Dónde has fallado"); filas=[]
        for tema,cantidad in errores.items():
            total_tema=sum(1 for p in st.session_state.preguntas if p[8]==tema); filas.append((tema.split('. ',1)[1] if '. ' in tema else tema,cantidad,total_tema,cantidad/total_tema if total_tema else 0))
        filas.sort(key=lambda x:x[3],reverse=True)
        for nombre,cantidad,total_tema,ratio in filas:
            st.markdown(f"**{nombre}** · {cantidad} fallos de {total_tema} ({ratio*100:.0f}%)"); st.progress(ratio)
        st.info(f"🎯 **Prioridad de repaso:** {filas[0][0]}. Te conviene reforzar este módulo antes de repetir el simulacro.")
    st.divider(); c1,c2=st.columns(2)
    with c1:
        if st.button("🧠 Repaso inteligente",use_container_width=True): iniciar_sesion("inteligente")
    with c2:
        if st.button("🏠 Volver al inicio",use_container_width=True): st.session_state.pantalla="dashboard"; st.rerun()

# ============================================================
# ESTADÍSTICAS
# ============================================================

def stats():
    st.markdown('<div class="titulo">📊 Tu progreso</div>',unsafe_allow_html=True); st.markdown('<div class="subtitulo">Una visión completa de tu preparación para el EIP</div>',unsafe_allow_html=True)
    if st.button("🏠 Volver al inicio"): st.session_state.pantalla="dashboard"; st.rerun()
    stats=get_global_stats(); modules=get_module_stats(); tab1,tab2,tab3=st.tabs(["📈 Resumen","📚 Módulos","⚠️ Debilidades"])
    with tab1:
        st.markdown("### Resumen global"); c1,c2,c3,c4=st.columns(4); c1.metric("Precisión",f"{stats['precision']*100:.0f}%"); c2.metric("Preguntas vistas",stats['vistas']); c3.metric("Dominadas",stats['dominadas']); c4.metric("Pendientes",stats['pendientes'])
        cobertura=stats['vistas']/stats['total'] if stats['total'] else 0; st.markdown("**Cobertura del banco**"); st.progress(cobertura); st.caption(f"{stats['vistas']} de {stats['total']} preguntas vistas ({cobertura*100:.0f}%)")
        st.markdown("### 📅 Evolución — últimos 30 días"); df=get_history_stats(30)
        if df['Preguntas'].sum()>0:
            st.line_chart(df.set_index('Fecha')[['Precisión']],height=260); c1,c2,c3=st.columns(3); c1.metric("Preguntas",int(df['Preguntas'].sum())); c2.metric("Tiempo",f"{df['Tiempo (min)'].sum():.0f} min"); c3.metric("Mejor racha",int(df['Racha'].max()))
        else: st.info("Aún no hay suficiente actividad para mostrar una evolución.")
        st.markdown("### 🧭 Índice de preparación"); indice=.50*stats['precision']+.25*cobertura+.25*(stats['dominadas']/stats['total'] if stats['total'] else 0); st.progress(min(indice,1.0)); st.markdown(f"## {indice*100:.0f} / 100")
        if indice>=.85: st.success("🌟 Nivel alto de preparación. Ahora conviene mantener y hacer simulacros.")
        elif indice>=.70: st.info("🟡 Buen progreso. Sigue aumentando cobertura y consolidando errores.")
        elif indice>=.50: st.warning("🟠 En progreso. Te interesa priorizar las áreas débiles.")
        else: st.warning("🔴 Todavía necesitas consolidar una parte importante del banco.")
        st.caption("Índice orientativo basado en precisión, cobertura del banco y preguntas dominadas; no representa una probabilidad real de aprobar.")
    with tab2:
        st.markdown("### Rendimiento por módulo")
        for m in modules:
            st.markdown(f"#### {m['emoji']} {m['nombre']} · {m['nivel']}"); c1,c2,c3=st.columns(3); c1.metric("Precisión",f"{m['precision']*100:.0f}%"); c2.metric("Cobertura",f"{m['cobertura']*100:.0f}%"); c3.metric("Dominadas",f"{m['dominadas']} / {m['total']}"); st.progress(m['cobertura']); st.caption(f"{m['vistas']} preguntas vistas · {m['aciertos']} aciertos · {m['fallos']} fallos")
        st.markdown("### Leyenda"); st.caption("⚪ No trabajado · 🔴 Débil · 🟡 En progreso · 🟢 Buen nivel · ⭐ Dominado")
    with tab3:
        st.markdown("### ⚠️ Tus preguntas más problemáticas"); weak=get_weak_questions(8)
        if not weak: st.success("🎉 Todavía no hay suficientes errores registrados.")
        else:
            for i,(enunciado,tema,aciertos,fallos,factor) in enumerate(weak,1):
                nombre=tema.split('. ',1)[1] if '. ' in tema else tema; intentos=aciertos+fallos; ratio=fallos/intentos if intentos else 0
                with st.container(border=True):
                    st.markdown(f"**{i}. {nombre}**"); st.write(enunciado); c1,c2,c3=st.columns(3); c1.metric("Fallos",fallos); c2.metric("Aciertos",aciertos); c3.metric("Tasa de fallo",f"{ratio*100:.0f}%")
        st.markdown("### 🎯 Qué estudiar ahora"); weak_modules=sorted(modules,key=lambda x:(x['precision'] if x['vistas'] else -1,-x['cobertura']))
        for m in weak_modules[:3]:
            if m['vistas']>0: st.write(f"**{m['nombre']}** — {m['precision']*100:.0f}% de precisión, {m['cobertura']*100:.0f}% de cobertura.")

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
