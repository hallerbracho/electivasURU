import streamlit as st
import google.generativeai as genai
import json
import random
import time

# --- Configuración de la Página ---
st.set_page_config(
    page_title="Quiz para practicar",
    page_icon="💡",
    layout="centered"
)

# --- Definición de Asignaturas y Temas ---
subjects = {
    "Ciberseguridad": "DEsafíos prácticos de ciberseguridad ambientados en casos reales", 
    "Planificación y administración de redes de comunicaciones": "Desafíos prácticos de planificación y administración redes TCP/IP ambientados en casos reales",
    "Criptografía y seguridad de redes": "Desafíos prácticos de criptografía ambientados en problemas reales de ingeniería de telecomunicaciones" #aritmética modular
}

# --- Cargar la API Key ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    API_KEY_CONFIGURED = True
except (KeyError, FileNotFoundError):
    st.error("🚨 Error: API Key de Google AI no encontrada.")
    st.error("Por favor, añade tu API Key de Google AI en el archivo `.streamlit/secrets.toml`.")
    st.markdown("Obtén tu clave en [Google AI Studio](https://aistudio.google.com/app/apikey).")
    st.markdown("El archivo `secrets.toml` debe contener:")
    st.code("""
GOOGLE_API_KEY="TU_CLAVE_AQUI"
    """)
    API_KEY_CONFIGURED = False
    st.stop()

# --- Inicialización del Estado de la Sesión ---
# Inicializar el estado de la sesión para la asignatura seleccionada si no existe
if 'selected_subject' not in st.session_state:
    st.session_state.selected_subject = None

# Inicializar el resto de las variables de estado del quiz si no existen 
if 'current_question' not in st.session_state:
    st.session_state.current_question = None
    st.session_state.question_requested = False
    st.session_state.user_answer = None
    st.session_state.submitted = False
    st.session_state.feedback = None
    st.session_state.correct_count = 0
    st.session_state.total_questions = 0
    st.session_state.max_questions = 12
    st.session_state.quiz_finished = False
    st.session_state.asked_questions_set = set()

# --- Pantalla de Selección de Asignatura ---
if st.session_state.selected_subject is None:
    st.image("https://uru.edu/wp-content/uploads/2023/02/uru-logo-maracaibo.png")
    st.subheader("Selecciona una Electiva", divider=True)
    # Usar un key único para el selectbox si es necesario en futuras expansiones
    selected_subject_name = st.selectbox(
        "Elige la asignatura electiva para el quiz:",
        options=list(subjects.keys()),
        index=None, # Inicia sin una opción seleccionada
        key="subject_select"
    )

    if selected_subject_name:
        st.session_state.selected_subject = selected_subject_name
        # Reiniciar el estado del quiz cuando se selecciona una nueva asignatura
        st.session_state.current_question = None
        st.session_state.question_requested = False
        st.session_state.user_answer = None
        st.session_state.submitted = False
        st.session_state.feedback = None
        st.session_state.correct_count = 0
        st.session_state.total_questions = 0
        st.session_state.quiz_finished = False
        st.session_state.asked_questions_set = set()
        st.rerun() # Rerun para pasar a la pantalla del quiz

else:
    # --- Modelo de IA y Configuraciones ---
    # Usamos gemini-2.0-flash-lite para mejor rendimiento y capacidad de seguir instrucciones.
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash-lite",
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2
        },
        safety_settings=[
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    )

    # Obtener el tema basado en la asignatura seleccionada
    current_subject = st.session_state.selected_subject
    current_theme = subjects[current_subject]


    # --- Funciones ---

    def generate_question_google(subject, theme): #ficticio
        """Llama a la API de Google Gemini para generar una pregunta con explicación."""
        prompt = f"""
            Genera una única pregunta técnica sobre la asignatura {subject} y el tema {theme}. La pregunta debe venir precedida por un escenario hipotético y desafiante relacionado con la pregunta.
            La pregunta debe ser de tipo selección múltiple ('mc') con 5 opciones.
            Responde ÚNICAMENTE con un objeto JSON válido que se adhiera ESTRICTAMENTE al siguiente formato, sin texto adicional antes o después del JSON.

            Formato Requerido:
            {{
              "question": "Escenario hipotético, doble salto de línea, Texto de la pregunta (en negritas)",
              "type": "mc",
              "options": ["Opción A", "Opción B", "Opción Correcta", "Opción D", "Opcion E"],
              "answer": "Texto de la Opción Correcta",
              "difficulty": "Fácil" | "Intermedio" | "Difícil",
              "explanation": "Explicación detallada (2-4 frases resaltando en negritas las palabras clave) de por qué la respuesta es correcta y, opcionalmente, contexto relevante o por qué las otras opciones son incorrectas. Usa viñetas."
            }}

            Asegúrate de que el valor de 'answer' sea la respuesta correcta (Opción Correcta) a la pregunta y que coincida exactamente con uno de los strings en el array 'options'.
            La explicación debe ser clara, extensa, educacional y en tono académico.
            La pregunta debe ser totalmente diferente a las preguntas generadas anteriormente en esta sesión de quiz. Si es similar, debes generar otra.
            Preguntas ya usadas (últimas 12 para contexto): {list(st.session_state.get('asked_questions_set', set()))[-12:]}
        """
        try:
            response = model.generate_content(prompt)
            json_text = response.text

            # --- Robustecer la limpieza del JSON ---
            json_text = json_text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:].strip()
            if json_text.endswith("```"):
                json_text = json_text[:-3].strip()
            # --- Fin limpieza ---

            question_data = json.loads(json_text)

            required_keys = ["question", "type", "options", "answer", "difficulty", "explanation"]
            if not all(key in question_data for key in required_keys):
                missing_keys = [key for key in required_keys if key not in question_data]
                raise ValueError(f"JSON generado no contiene todas las claves requeridas. Faltan: {missing_keys}")

            if not isinstance(question_data["options"], list):
                 raise ValueError("El campo 'options' debe ser una lista.")
            if question_data["type"] == "mc" and question_data["answer"] not in question_data["options"]:
                 raise ValueError("La respuesta ('answer') no está en las opciones ('options') para tipo 'mc'.")
            if question_data["type"] == "tf" and question_data["answer"] not in ["Verdadero", "Falso"]:
                 raise ValueError("La respuesta ('answer') debe ser 'Verdadero' o 'Falso' para tipo 'tf'.")

            explanation = question_data.get("explanation", "")
            if not isinstance(explanation, str) or len(explanation) < 50:
                 st.warning(f"La explicación generada parece muy corta o inválida ({len(explanation)} caracteres).")

            if question_data["type"] == 'mc':
                 random.shuffle(question_data["options"])

            return question_data

        except json.JSONDecodeError as e:
            st.error(f"😥 Error al decodificar JSON de la IA: {e}")
            st.text_area("Texto recibido (para depuración):", json_text, height=150)
            try: st.text_area("Detalles del Response (si disponibles):", str(response), height=100) # type: ignore
            except: pass
            return None
        except ValueError as e:
            st.error(f"😥 Error de validación en JSON generado: {e}")
            try: st.json(question_data) # type: ignore
            except: st.text_area("Datos generados (no JSON válido):", str(question_data))
            return None
        except Exception as e:
            st.error(f"😥 Error general al generar pregunta con Google AI: {e}")
            try: st.error(f"Detalles adicionales: {response.prompt_feedback}") # type: ignore
            except: pass
            return None


    # --- Diseño de la Interfaz del Quiz ---
    with st.container():
        coll1, coll2 = st.columns([1,2])
        with coll1:
            st.image("https://uru.edu/wp-content/uploads/2023/02/uru-logo-maracaibo.png") #
        with coll2:
            st.subheader(f'{current_subject}')
        st.markdown(f"**{st.session_state.max_questions} preguntas** para practicar y certificar tus conocimientos en {current_subject}.")

    main_interaction_area = st.container(border=True)
    score_area = st.container()

    # --- Lógica Principal del Quiz ---

    # --- Display Principal (Pregunta/Feedback o Resultado Final) ---
    with main_interaction_area:
        # --- Estado 1: Quiz NO terminado ---
        if not st.session_state.quiz_finished:
            # 1. Generar nueva pregunta si es necesario
            if st.session_state.current_question is None and not st.session_state.question_requested:
                if st.session_state.total_questions < st.session_state.max_questions:
                    st.session_state.question_requested = True
                    with st.spinner("🧠 Generando pregunta única y explicación..."):
                        new_question = None
                        max_attempts = 5
                        attempts = 0
                        while attempts < max_attempts:
                            attempts += 1
                            # Pasar la asignatura y el tema a la función de generación
                            generated_data = generate_question_google(current_subject, current_theme)
                            if generated_data:
                                question_text = generated_data['question']
                                if question_text not in st.session_state.asked_questions_set:
                                    new_question = generated_data
                                    st.session_state.asked_questions_set.add(question_text)
                                    break
                                else:
                                    time.sleep(0.5)
                            else:
                                time.sleep(1)

                        if new_question:
                            st.session_state.current_question = new_question
                            st.session_state.user_answer = None
                            st.session_state.submitted = False
                            st.session_state.feedback = None
                            st.session_state.question_requested = False
                            st.rerun()
                        else:
                            st.error(f"❌ No se pudo generar una pregunta ÚNICA y válida después de {max_attempts} intentos.")
                            st.session_state.question_requested = False

                elif st.session_state.total_questions == st.session_state.max_questions and not st.session_state.quiz_finished:
                     st.session_state.quiz_finished = True
                     st.session_state.current_question = None
                     st.session_state.user_answer = None
                     st.session_state.submitted = False
                     st.session_state.feedback = None
                     st.session_state.question_requested = False
                     st.rerun()

            # 2. Mostrar Pregunta/Opciones O Feedback/Explicación
            if st.session_state.current_question:
                q_data = st.session_state.current_question

                # ---- Estado: Mostrando Pregunta ----
                if not st.session_state.submitted:
                    #cl1, cl2 = st.columns([2,1])
                    #with cl1:
                    st.subheader(f"Pregunta {st.session_state.total_questions + 1} de {st.session_state.max_questions}", divider=True)
                    #with cl2:
                        #st.markdown(" ")
                    st.markdown(f"{q_data['question']}")
                    st.badge(f"Dificultad: {q_data.get('difficulty', 'No especificada')}", color="gray")

                    options = q_data['options']
                    user_answer = st.radio(
                        "Elige tu respuesta:", options, index=None,
                        key=f"q_{st.session_state.total_questions}",
                        label_visibility="collapsed"
                    )
                    st.session_state.user_answer = user_answer

                    col1, col2, col3 = st.columns([1,2,1])
                    with col2:
                        submit_button_disabled = (user_answer is None)
                        if st.button("✔️ Enviar Respuesta", disabled=submit_button_disabled, use_container_width=True):
                            st.session_state.submitted = True
                            correct_answer = q_data['answer']
                            if st.session_state.user_answer == correct_answer:
                                st.session_state.feedback = "✅ ¡Correcto!"
                                st.session_state.correct_count += 1
                            else:
                                st.session_state.feedback = f"❌ Incorrecto."
                            st.session_state.total_questions += 1
                            st.rerun()

                # ---- Estado: Mostrando Feedback y Explicación ----
                elif st.session_state.submitted and st.session_state.feedback:
                    if "✅" in st.session_state.feedback:
                        st.success(st.session_state.feedback, icon="🎉")
                    else:
                        st.error(f"{st.session_state.feedback} La respuesta correcta era: **{q_data['answer']}**", icon="🤔")

                    explanation = q_data.get("explanation", "No se pudo generar una explicación para esta pregunta.")
                    with st.container(border=True):
                        st.markdown(f"**Explicación:**")
                        st.markdown(explanation)

                    col1, col2, col3 = st.columns([1,1,1])
                    with col2:
                        if st.session_state.total_questions < st.session_state.max_questions:
                            if st.button("➡️ Siguiente Pregunta", use_container_width=True):
                                st.session_state.current_question = None
                                st.session_state.user_answer = None
                                st.session_state.submitted = False
                                st.session_state.feedback = None
                                st.session_state.question_requested = False
                                st.rerun()
                        else:
                            if st.button("🏆 Ver Resultados Finales", use_container_width=True):
                                st.session_state.quiz_finished = True
                                st.session_state.current_question = None
                                st.session_state.user_answer = None
                                st.session_state.submitted = False
                                st.session_state.feedback = None
                                st.rerun()

            # Message if no question is loaded yet
            elif API_KEY_CONFIGURED and st.session_state.current_question is None and not st.session_state.question_requested:
                 st.info("Haz click en 'Reiniciar Quiz' o espera a que se genere la primera pregunta.")

        # --- Estado 2: Quiz TERMINADO ---
        elif st.session_state.quiz_finished:
            st.subheader("🥳 ¡Quiz Terminado!")
            st.balloons()

            final_score = st.session_state.correct_count
            total_possible = st.session_state.max_questions
            final_accuracy = (final_score / total_possible * 100) if total_possible > 0 else 0

            st.markdown(f"Has completado las {total_possible} preguntas.")
            st.markdown(f"Tu resultado final es:")

            col_score, col_accuracy, c3 = st.columns(3)
            with col_score:
                st.metric("Aciertos", final_score, delta_color="normal", border=True)
            with col_accuracy:
                 st.metric("Porcentaje de Aciertos", f"{final_accuracy:.1f}%", delta_color="normal", border=True)

            with c3:
                 nota2 = final_accuracy*20/100
                 st.metric("Calificación", f"{nota2:.1f}", border=True)

            st.markdown("¿Quieres intentarlo de nuevo?")

            # Botón para Reiniciar el Quiz
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                # Modificado: Añadir botón para volver a seleccionar asignatura
                if st.button("🔁 Reiniciar Quiz y Seleccionar Asignatura", use_container_width=True):
                    # Reset ALL relevant session state variables including selected_subject
                    st.session_state.current_question = None
                    st.session_state.question_requested = False
                    st.session_state.user_answer = None
                    st.session_state.submitted = False
                    st.session_state.feedback = None
                    st.session_state.correct_count = 0
                    st.session_state.total_questions = 0
                    st.session_state.quiz_finished = False
                    st.session_state.asked_questions_set = set()
                    st.session_state.selected_subject = None # Crucial: Reset selected subject
                    st.rerun()

    # 3. Mostrar Marcador (visible durante el quiz)
    with score_area:
         if not st.session_state.quiz_finished:
             col1, col2, col3 = st.columns(3)
             with col1:
                 valor = st.session_state.max_questions - st.session_state.total_questions
                 st.metric("Preguntas Contestadas", f"{st.session_state.total_questions} / {st.session_state.max_questions}", f"{valor} pregunta(s) restantes", border=True, delta_color="off")
             with col2:
                 accuracy = (st.session_state.correct_count / st.session_state.total_questions * 100) if st.session_state.total_questions > 0 else 0
                 st.metric("Aciertos", f"{st.session_state.correct_count}", f"{accuracy:.1f}%", border=True)
             with col3:
                nota = accuracy*20/100
                st.metric("Calificación", f"{nota:.1f}", "puntos", border=True)


# --- Footer ---
st.caption("Escuela de Telecomunicaciones y Computación de la Facultad de Ingeniería de la Universidad Rafael Urdaneta")
