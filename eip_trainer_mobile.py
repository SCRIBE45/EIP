import sqlite3
import random
import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView


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


class EIPDatabase:
    """Lógica de datos independiente de la interfaz móvil."""

    def __init__(self, db_path="examen.db"):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.setup_db()

    def setup_db(self):
        self.cursor.execute("PRAGMA table_info(Preguntas)")
        columnas = [col[1] for col in self.cursor.fetchall()]

        nuevas_columnas = {
            "ultima_vista": "TEXT",
            "veces_acertada": "INTEGER DEFAULT 0",
            "veces_fallada": "INTEGER DEFAULT 0",
            "intervalo": "INTEGER DEFAULT 0",
            "proxima_revision": "TEXT",
            "factor_facilidad": "REAL DEFAULT 2.5",
        }

        # Si la tabla Preguntas ya existe, conserva su estructura y añade
        # las columnas que necesita el algoritmo.
        if columnas:
            for col, tipo in nuevas_columnas.items():
                if col not in columnas:
                    self.cursor.execute(
                        f"ALTER TABLE Preguntas ADD COLUMN {col} {tipo}"
                    )

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS RegistroDiario (
                fecha TEXT PRIMARY KEY,
                respondidas INTEGER DEFAULT 0,
                acertadas INTEGER DEFAULT 0,
                tiempo_segundos INTEGER DEFAULT 0,
                racha_maxima INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def actualizar_registro_diario(self, acertada, tiempo_gastado=0, racha=0):
        hoy = datetime.date.today().isoformat()
        self.cursor.execute(
            """SELECT respondidas, acertadas, tiempo_segundos, racha_maxima
               FROM RegistroDiario WHERE fecha = ?""",
            (hoy,),
        )
        registro = self.cursor.fetchone()

        if registro:
            resp, acert, tiempo, racha_max = registro
            self.cursor.execute(
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
            self.cursor.execute(
                """INSERT INTO RegistroDiario
                   (fecha, respondidas, acertadas, tiempo_segundos, racha_maxima)
                   VALUES (?, ?, ?, ?, ?)""",
                (hoy, 1, 1 if acertada else 0, tiempo_gastado, racha),
            )
        self.conn.commit()

    def actualizar_algoritmo(
        self, id_preg, es_correcta, aciertos, fallos, intervalo, factor, modo, racha
    ):
        if es_correcta:
            aciertos += 1
            intervalo = (
                1 if aciertos == 1
                else 3 if aciertos == 2
                else round(intervalo * factor)
            )
            factor = min(3.0, factor + 0.1)
        else:
            aciertos = 0
            fallos += 1
            intervalo = 0
            factor = max(1.3, factor - 0.2)

        hoy = datetime.date.today()
        proxima = (hoy + datetime.timedelta(days=intervalo)).isoformat()

        self.cursor.execute(
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
        self.conn.commit()

        if modo != "simulacro":
            self.actualizar_registro_diario(
                acertada=es_correcta, tiempo_gastado=15, racha=racha
            )

    def get_today_stats(self):
        hoy = datetime.date.today().isoformat()
        self.cursor.execute(
            """SELECT respondidas, acertadas, tiempo_segundos, racha_maxima
               FROM RegistroDiario WHERE fecha = ?""",
            (hoy,),
        )
        return self.cursor.fetchone()

    def get_questions(self, modo, tema):
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

        self.cursor.execute(query, parametros)
        return self.cursor.fetchall()

    def get_module_stats(self):
        resultado = []

        for tema in TEMAS_OFICIALES[1:]:
            self.cursor.execute(
                """SELECT COUNT(*), SUM(veces_fallada), SUM(veces_acertada)
                   FROM Preguntas WHERE tema = ?""",
                (tema,),
            )
            total, fallos, aciertos = self.cursor.fetchone()
            fallos = fallos or 0
            aciertos = aciertos or 0
            porc = (
                aciertos / (aciertos + fallos)
                if (aciertos + fallos) > 0 else 0
            )
            resultado.append((tema, total, porc))

        return resultado


class DashboardScreen(Screen):
    pass


class SessionScreen(Screen):
    pass


class ResultsScreen(Screen):
    pass


class StatsScreen(Screen):
    pass


class EIPMobileApp(App):
    modo = StringProperty("")
    pregunta_texto = StringProperty("")
    tema_texto = StringProperty("")
    progreso_texto = StringProperty("")
    resultado_texto = StringProperty("")
    explicacion_texto = StringProperty("")
    temporizador_texto = StringProperty("")
    aciertos = NumericProperty(0)
    racha_actual = NumericProperty(0)

    def build(self):
        self.title = "EIP Trainer"
        self.db = EIPDatabase("examen.db")

        self.preguntas_sesion = []
        self.indice_actual = 0
        self.tiempo_restante = 3600
        self.timer_event = None
        self.errores_simulacro = {}

        self.sm = ScreenManager()
        self.dashboard = DashboardScreen(name="dashboard")
        self.session = SessionScreen(name="session")
        self.results = ResultsScreen(name="results")
        self.stats = StatsScreen(name="stats")

        self.sm.add_widget(self.dashboard)
        self.sm.add_widget(self.session)
        self.sm.add_widget(self.results)
        self.sm.add_widget(self.stats)

        self.build_dashboard()
        self.build_session()
        self.build_results()
        self.build_stats()

        self.update_dashboard()
        return self.sm

    # ---------------- UI ----------------

    def make_button(self, text, callback, height=dp(58)):
        b = Button(
            text=text,
            size_hint_y=None,
            height=height,
            font_size=dp(16),
        )
        b.bind(on_release=callback)
        return b

    def build_dashboard(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(12),
        )

        root.add_widget(Label(
            text="📚 EIP Trainer",
            font_size=dp(30),
            bold=True,
            size_hint_y=None,
            height=dp(55),
        ))

        root.add_widget(Label(
            text="Preparación para el European Investment Practitioner",
            font_size=dp(14),
            size_hint_y=None,
            height=dp(35),
        ))

        self.today_label = Label(
            text="",
            font_size=dp(15),
            size_hint_y=None,
            height=dp(55),
        )
        root.add_widget(self.today_label)

        root.add_widget(Label(
            text="Seleccionar módulo",
            bold=True,
            size_hint_y=None,
            height=dp(30),
        ))

        self.topic_spinner = Spinner(
            text="Todos los temas",
            values=TEMAS_OFICIALES,
            size_hint_y=None,
            height=dp(52),
            font_size=dp(14),
        )
        root.add_widget(self.topic_spinner)

        root.add_widget(self.make_button(
            "📝  SIMULACRO — 40 preguntas",
            lambda *_: self.start_session("simulacro"),
        ))
        root.add_widget(self.make_button(
            "🧠  REPASO INTELIGENTE",
            lambda *_: self.start_session("inteligente"),
        ))
        root.add_widget(self.make_button(
            "🔄  SOLO FALLADAS",
            lambda *_: self.start_session("falladas"),
        ))
        root.add_widget(self.make_button(
            "🎲  PRÁCTICA LIBRE",
            lambda *_: self.start_session("libre"),
        ))
        root.add_widget(self.make_button(
            "📊  ESTADÍSTICAS",
            self.show_stats,
        ))

        self.dashboard.add_widget(root)

    def build_session(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
        )

        top = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )

        top.add_widget(self.make_button("⌂ Inicio", self.go_home, dp(48)))

        self.mode_label = Label(
            text="",
            font_size=dp(14),
            bold=True,
        )
        top.add_widget(self.mode_label)

        self.progress_label = Label(
            text="",
            font_size=dp(14),
            size_hint_x=0.55,
        )
        top.add_widget(self.progress_label)

        self.timer_label = Label(
            text="",
            font_size=dp(15),
            bold=True,
            size_hint_x=0.45,
        )
        top.add_widget(self.timer_label)

        root.add_widget(top)

        self.progress_bar = ProgressBar(
            max=1,
            value=0,
            size_hint_y=None,
            height=dp(8),
        )
        root.add_widget(self.progress_bar)

        self.theme_label = Label(
            text="",
            font_size=dp(13),
            size_hint_y=None,
            height=dp(35),
        )
        root.add_widget(self.theme_label)

        # Scroll para preguntas largas y pantallas pequeñas.
        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=(0, dp(10)),
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        self.question_label = Label(
            text="",
            font_size=dp(19),
            bold=True,
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self.question_label.bind(
            width=lambda obj, value: setattr(obj, "text_size", (value, None))
        )
        self.question_label.bind(
            texture_size=lambda obj, value: setattr(obj, "height", value[1] + dp(10))
        )
        content.add_widget(self.question_label)

        self.option_buttons = {}
        for letter in "ABCD":
            btn = Button(
                text="",
                font_size=dp(16),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(72),
            )
            btn.bind(
                width=lambda obj, value: setattr(obj, "text_size", (value - dp(25), None))
            )
            btn.bind(on_release=lambda obj, l=letter: self.check_answer(l))
            self.option_buttons[letter] = btn
            content.add_widget(btn)

        self.feedback_label = Label(
            text="",
            font_size=dp(17),
            bold=True,
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self.feedback_label.bind(
            width=lambda obj, value: setattr(obj, "text_size", (value, None))
        )
        self.feedback_label.bind(
            texture_size=lambda obj, value: setattr(obj, "height", value[1] + dp(10))
        )
        content.add_widget(self.feedback_label)

        self.explanation_label = Label(
            text="",
            font_size=dp(15),
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self.explanation_label.bind(
            width=lambda obj, value: setattr(obj, "text_size", (value, None))
        )
        self.explanation_label.bind(
            texture_size=lambda obj, value: setattr(obj, "height", value[1] + dp(10))
        )
        content.add_widget(self.explanation_label)

        self.next_button = self.make_button(
            "Siguiente ➜",
            self.next_question,
            dp(58),
        )
        content.add_widget(self.next_button)

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.session.add_widget(root)

    def build_results(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(25),
            spacing=dp(20),
        )

        root.add_widget(Label(
            text="Resultados",
            font_size=dp(28),
            bold=True,
            size_hint_y=None,
            height=dp(60),
        ))

        self.results_label = Label(
            text="",
            font_size=dp(18),
            halign="center",
            valign="middle",
        )
        self.results_label.bind(
            width=lambda obj, value: setattr(obj, "text_size", (value, None))
        )
        root.add_widget(self.results_label)

        root.add_widget(self.make_button("🏠 Volver al inicio", self.go_home))

        self.results.add_widget(root)

    def build_stats(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(15),
        )

        root.add_widget(self.make_button("⌂ Inicio", self.go_home, dp(48)))

        root.add_widget(Label(
            text="Rendimiento histórico por módulos",
            font_size=dp(24),
            bold=True,
            size_hint_y=None,
            height=dp(60),
        ))

        scroll = ScrollView()
        self.stats_box = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            size_hint_y=None,
            padding=(0, dp(10)),
        )
        self.stats_box.bind(minimum_height=self.stats_box.setter("height"))

        scroll.add_widget(self.stats_box)
        root.add_widget(scroll)

        self.stats.add_widget(root)

    # ---------------- LÓGICA ----------------

    def update_dashboard(self):
        reg = self.db.get_today_stats()

        if reg and reg[0] > 0:
            respondidas, acertadas, tiempo, racha = reg
            porc = acertadas / respondidas * 100
            self.today_label.text = (
                f"Hoy: 📝 {respondidas} | 🎯 {porc:.1f}% | "
                f"⏱ {tiempo // 60} min | 🔥 {racha}"
            )
        else:
            self.today_label.text = (
                "Hoy: 📝 0 preguntas | 🎯 0% | ⏱ 0 min | 🔥 0"
            )

    def start_session(self, modo):
        self.modo = modo
        self.tiempo_restante = 3600
        self.aciertos = 0
        self.racha_actual = 0
        self.indice_actual = 0

        self.errores_simulacro = {
            t: 0 for t in TEMAS_OFICIALES[1:]
        }

        tema = self.topic_spinner.text
        self.preguntas_sesion = self.db.get_questions(modo, tema)

        self.mode_label.text = {
            "simulacro": "📝 Simulacro",
            "inteligente": "🧠 Repaso",
            "falladas": "🔄 Falladas",
            "libre": "🎲 Libre",
        }.get(modo, modo)

        self.sm.current = "session"

        if self.timer_event:
            self.timer_event.cancel()
            self.timer_event = None

        if modo == "simulacro":
            self.timer_event = Clock.schedule_interval(
                self.update_timer, 1
            )
        else:
            self.timer_label.text = ""

        if not self.preguntas_sesion:
            self.question_label.text = (
                "No hay preguntas disponibles para este modo/filtro."
            )
            for btn in self.option_buttons.values():
                btn.disabled = True
            self.next_button.disabled = True
            return

        self.load_question()

    def load_question(self):
        if self.indice_actual >= len(self.preguntas_sesion):
            self.show_results()
            return

        p = self.preguntas_sesion[self.indice_actual]

        self.progress_label.text = (
            f"Pregunta {self.indice_actual + 1}/{len(self.preguntas_sesion)}"
        )
        self.progress_bar.value = (
            (self.indice_actual + 1) / len(self.preguntas_sesion)
        )

        self.theme_label.text = p[8]
        self.question_label.text = p[1]

        for letter, index in zip("ABCD", [2, 3, 4, 5]):
            btn = self.option_buttons[letter]
            btn.text = f"{letter}) {p[index]}"
            btn.disabled = False

        self.feedback_label.text = ""
        self.explanation_label.text = ""
        self.next_button.disabled = True

    def check_answer(self, seleccion):
        p = self.preguntas_sesion[self.indice_actual]
        correcta = p[6]
        es_correcta = seleccion == correcta

        for btn in self.option_buttons.values():
            btn.disabled = True

        if es_correcta:
            self.aciertos += 1
            self.racha_actual += 1
            self.feedback_label.text = "✅ ¡Correcto!"
        else:
            self.racha_actual = 0
            self.feedback_label.text = (
                f"❌ Incorrecto. La respuesta correcta era la {correcta}."
            )

            if self.modo == "simulacro":
                self.errores_simulacro[p[8]] += 1

        self.db.actualizar_algoritmo(
            p[0],
            es_correcta,
            p[9],
            p[10],
            p[11],
            p[12],
            self.modo,
            self.racha_actual,
        )

        if p[7] and p[7].strip():
            self.explanation_label.text = f"💡 Explicación:\n\n{p[7]}"
        else:
            self.explanation_label.text = ""

        if self.modo == "simulacro":
            self.indice_actual += 1
            self.load_question()
        else:
            self.next_button.disabled = False

    def next_question(self, *_):
        if self.indice_actual + 1 < len(self.preguntas_sesion):
            pendientes = self.preguntas_sesion[self.indice_actual + 1:]

            if self.racha_actual >= 5:
                pendientes.sort(key=lambda x: (x[12], -x[10]))
            elif self.racha_actual == 0:
                pendientes.sort(key=lambda x: (-x[12], x[9]))
            else:
                random.shuffle(pendientes)

            self.preguntas_sesion[self.indice_actual + 1:] = pendientes

        self.indice_actual += 1
        self.load_question()

    def update_timer(self, dt):
        if self.modo != "simulacro":
            return

        if self.tiempo_restante <= 0:
            self.show_results()
            return

        m, s = divmod(self.tiempo_restante, 60)
        self.timer_label.text = f"⏱ {m:02d}:{s:02d}"
        self.tiempo_restante -= 1

    def show_results(self):
        if self.timer_event:
            self.timer_event.cancel()
            self.timer_event = None

        total = len(self.preguntas_sesion)
        nota = self.aciertos / total * 10 if total else 0

        if self.modo == "simulacro":
            t_usado = 3600 - self.tiempo_restante
            self.db.actualizar_registro_diario(
                acertada=False,
                tiempo_gastado=t_usado,
                racha=self.racha_actual,
            )

            texto = (
                "🏆 SIMULACRO FINALIZADO 🏆\n\n"
                f"⏱ Tiempo: {t_usado // 60:02d}:{t_usado % 60:02d}\n"
                f"✅ Aciertos: {self.aciertos} de {total}\n"
                f"🎓 Nota: {nota:.1f} / 10\n\n"
            )

            errores = sum(self.errores_simulacro.values())
            if errores:
                texto += "📉 Errores por tema:\n"
                for tema, err in self.errores_simulacro.items():
                    if err:
                        texto += f"• {tema}: {err} fallos\n"
        else:
            texto = (
                "🎉 ¡Sesión terminada! 🎉\n\n"
                f"✅ Aciertos: {self.aciertos} de {total}\n"
                f"🎓 Nota equivalente: {nota:.1f} / 10"
            )

        self.results_label.text = texto
        self.sm.current = "results"
        self.update_dashboard()

    def show_stats(self, *_):
        for child in list(self.stats_box.children):
            self.stats_box.remove_widget(child)

        for tema, total, porc in self.db.get_module_stats():
            nombre = tema.split(". ", 1)[1] if ". " in tema else tema

            self.stats_box.add_widget(Label(
                text=f"{nombre}\n{int(porc * 100)}%   ({total} preguntas)",
                font_size=dp(16),
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(70),
            ))

            bar = ProgressBar(
                max=1,
                value=porc,
                size_hint_y=None,
                height=dp(10),
            )
            self.stats_box.add_widget(bar)

        self.sm.current = "stats"

    def go_home(self, *_):
        if self.timer_event:
            self.timer_event.cancel()
            self.timer_event = None
        self.update_dashboard()
        self.sm.current = "dashboard"


if __name__ == "__main__":
    EIPMobileApp().run()
