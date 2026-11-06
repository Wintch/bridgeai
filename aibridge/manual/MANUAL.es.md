# Tu Hermes: manual de bienvenida

## 1. Qué es y cómo hablarle

Hermes es tu asistente personal. Es solo tuyo: tiene su propio espacio, sus propias memorias y sus propios archivos.

Lo usás por Telegram y también por un chat web. Escribile como a una persona. Podés mandarle texto, audios, fotos, videos y archivos.

Mientras trabaja, podés seguir escribiendo. Está pensado para que nada se pierda: te lo atiende en cuanto puede. Si algo se pierde, contalo con `/opinion`.

## 2. Qué puede hacer

**Lo básico, siempre prendido:**

- navegar por internet y leer páginas
- bajar videos y audios, y trabajar con YouTube
- entender tus notas de voz (audio a texto)
- consultas simples: clima, dólar, feriados, noticias
- mapas, lugares y recorridos

**Grupos que se prenden cuando vos querés.** Al principio solo está lo básico. Si pedís algo que no está, Hermes te dice qué grupo hace falta y te pregunta. Nunca prende uno solo.

- `edicion`: editar y convertir video, audio e imágenes; entender un video; identificar canciones.
- `creativo`: generar imágenes, infografías, diagramas, animaciones, música y GIFs.
- `empleo`: buscar y evaluar ofertas, adaptar tu CV, seguir postulaciones.
- `presupuesto`: impuestos, servicios y gastos del día a día en Argentina; seguimiento de precios.
- `oficina`: PDF, Word, Excel, PowerPoint, reuniones, correo, Google Workspace, Notion y similares.
- `investigacion`: papers, citas con fuente, wiki propia, seguimiento de competidores y de X.
- `programacion`: agentes de código, revisión, pruebas, GitHub.
- `codigos`: leer y crear códigos QR y de barras desde fotos o videos.
- `seguridad`: revisar si un archivo bajado figura como amenaza conocida. Solo viaja el hash del archivo; la segunda lista pide tu propia clave gratis de abuse.ch (opcional).
- `sitio`: editar y publicar tu sitio web, solo donde está configurado.
- `servidores`: diagnóstico de red y vista de solo lectura de Proxmox, solo donde el administrador lo configuró.

Para prender uno: `/paquete NOMBRE si`. Para apagarlo: `/paquete NOMBRE no`. Se aplica en la próxima conversación, o sea con `/new`.

Tener menos grupos prendidos lo hace más liviano y sus respuestas salen un poco más rápido. Prendé solo lo que usás.

## 3. Comandos

**Hablar**

- `/idioma es|ru|en|auto`: en qué idioma te contesta.
- `/voz`: con qué voz te manda los audios.
- `/btw PREGUNTA`: una pregunta al margen, sin cortar lo que está haciendo.
- `/stop`: frena la respuesta actual.
- `/new`: empieza una conversación nueva. Tus memorias quedan.
- `/retry`: vuelve a intentar con tu último mensaje.
- `/undo [N]`: deshace tus últimos N mensajes (1 si no decís cuántos).
- `/model`: elegir otro modelo para esta conversación.

**Trabajos**

- `/trabajos`: qué está corriendo ahora y cómo van los subtítulos.
- `/parar`: frena las descargas (`/parar subs` solo subtítulos).
- `/retomar`: sigue con los subtítulos de los canales ya empezados.
- `/archivos TEXTO`: busca un archivo que mandaste o que se bajó, aunque ya no esté.
- `/dormir`: se apaga de verdad. Si hay trabajo, te pregunta: `/dormir ya`, `/dormir luego` o `/dormir cancelar`.

**Ajustes**

- `/avisos diario|nuevo|no`: avisos de ofertas de trabajo.
- `/paquetes`: tus grupos activos. `/paquete NOMBRE si|no`: prender o apagar uno.
- `/compartir`: qué compartís con el administrador (ver más abajo).
- `/estado`: qué anda ahora y dónde corre cada cosa.

**Ayuda**

- `/manual`: este manual, en el chat.
- `/opinion TEXTO`: una nota para el administrador.
- `/opinion privado TEXTO`: una nota solo tuya.
- `/controles`: la lista de controles propios de Hermes.
- `/commands`: la lista completa de comandos (incluye muchos técnicos).

## 4. Tus claves

Algunos servicios piden una clave personal: una llave que te da cada servicio, casi siempre gratis. Cada persona consigue y paga las suyas.

- Las cargás en la página **Tus claves** o pidiéndole a Hermes que guarde tu clave de ese servicio.
- **Nunca pegues una clave en el chat.** Va en esa página.
- Solo tu Hermes la usa; el administrador no la usa ni la comparte.
- Podés borrarla cuando quieras.
- El administrador no usa ni comparte las claves que cargás vos. Si no cargás una clave de IA propia, algunos modelos gratis corren con una clave compartida del servidor.

Sin claves opcionales todo anda igual, con menos extras. Para chatear hace falta al menos una clave de IA: la tuya o, en algunos modelos gratis, la compartida del servidor. `/estado` te muestra qué funciona ahora.

## 5. Qué comparte y con quién

**Con quién pasan tus mensajes**

- La empresa que corre el modelo de IA que te contesta procesa lo que le escribís. Con modelos gratis, algunos proveedores pueden guardar y usar lo que mandás para entrenar.
- Las notas de voz las convierte en texto un servicio de voz.
- Las fotos las describe primero otro modelo.

**Con el administrador: `/compartir`**

Con `/compartir` ves tu nivel actual. Podés cambiarlo cuando quieras:

- `/compartir nada`: el administrador no mira cómo lo usás para mejorarlo, ni siquiera conteos. El servidor igual guarda los registros técnicos que necesita para funcionar, sin el texto de tus conversaciones.
- `/compartir uso` (el nivel por defecto): puede ver qué herramientas se usaron, cuántas veces, errores, tiempos y qué modelo contestó. Nunca el texto de tus mensajes ni el contenido de tus archivos.
- `/compartir todo`: puede leer la conversación para encontrar qué falló, solo para mejorar el asistente. Las claves y los textos largos que parecen secretos se tapan en lo que lee.

Una cosa dicha sin vueltas: el administrador es quien maneja el servidor. Estos niveles son un acuerdo sobre qué mira, no una barrera técnica.

## 6. Cómo opinar

- Reaccioná con 👍 o 👎 a cualquier respuesta. La reacción cuenta como un voto para el modelo que contestó; el voto no incluye el texto de la respuesta.
- `/opinion TEXTO`: para contar con palabras qué anduvo bien o mal. Lo lee el administrador para mejorar el asistente.
- `/opinion privado TEXTO`: queda solo en tu espacio; el administrador no lo lee ni lo recibe.

## 7. Cuando duerme

Si no lo usás durante unos 10 minutos, Hermes se duerme para ahorrar recursos de la máquina. Está pensado para que nada se pierda.

El primer mensaje después de dormir tarda unos 20 a 30 segundos. Es normal.

Con `/dormir` lo dormís vos, de verdad. Si dejaste prendida una ubicación en vivo de Telegram, no hace nada mientras duerme: conviene apagarla.

## 8. Límites

- Una revisión de archivos que no encuentra nada **no prueba que esté a salvo**: solo que no figura como amenaza conocida.
- Hermes tiene que decirte cuando no revisó algo. Si no lo dice, preguntale.
- Puede equivocarse. Verificá los datos importantes: plata, salud, temas legales.
- Corta una respuesta con `/stop`; las descargas, con `/parar`.

Este manual: /manual, o pedile a Hermes «mandame el manual en PDF».
