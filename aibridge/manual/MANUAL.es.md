# Tu Hermes: manual de bienvenida

## 1. Qué es y cómo hablarle

Hermes es tu asistente personal. Es solo tuyo: tiene su propio espacio, sus propias memorias y sus propios archivos.

Lo usás por Telegram y también por un chat web. Escribile como a una persona. Podés mandarle texto, audios, fotos, videos y archivos.

Mientras trabaja, podés seguir escribiendo; nada se pierde. Si algo se pierde, contalo con `/feedback`.

## 2. Qué puede hacer

**Lo básico, siempre prendido:**

- navegar por internet y leer páginas
- bajar videos y audios, y trabajar con YouTube
- entender tus notas de voz (audio a texto)
- consultas simples: clima, dólar, feriados, noticias
- mapas, lugares y recorridos

**Grupos que se prenden cuando vos querés.** Al principio solo está lo básico. Si pedís algo que no está, Hermes te dice qué grupo hace falta y te pregunta. Nunca prende uno solo.

- `edicion`: editar y convertir video, audio e imágenes; entender un video; identificar canciones.
- `mundo`: reconocer la canción que suena en un video o una nota de voz (con tu propia clave de AudD o ACRCloud); más adelante, intérprete. Los mapas y el clima ya vienen siempre.
- `revista`: cada mañana, lo importante de los canales de Telegram, blogs y noticias que seguís, con los avisos urgentes primero.
- `creativo`: generar imágenes, infografías, diagramas, animaciones, música y GIFs.
- `empleo`: buscar y evaluar ofertas, adaptar tu CV, seguir postulaciones.
- `presupuesto`: impuestos, servicios y gastos del día a día en Argentina; seguimiento de precios.
- `oficina`: PDF, Word, Excel, PowerPoint, reuniones, correo, Google Workspace, Notion y similares.
- `investigacion`: papers, citas con fuente, wiki propia, seguimiento de competidores y de X.
- `programacion`: agentes de código, revisión, pruebas, GitHub.
- `codigos`: leer y crear códigos QR y de barras desde fotos o videos.
- `seguridad`: buscar virus en un archivo bajado o enviado: si figura como amenaza conocida (solo viaja el hash; la segunda lista pide tu propia clave gratis de abuse.ch, opcional) y un análisis del contenido en este servidor (de segundos a unos minutos; el archivo no sale de acá). Un resultado sin detecciones no prueba que sea seguro.
- `sitio`: editar y publicar tu sitio web, solo donde está configurado.
- `sysadmin`: cuidar tus sitios y servidores: qué ve cualquiera de tu sitio, aviso antes de que venza una clave, consejos que citan la guía de seguridad. Red y Proxmox donde está configurado. (Antes `servidores`.)
- `maquinas`: una máquina remota con crédito: ver su estado y su pantalla. Encenderla, entrar y soltarla lo hacés vos con `/machine on`, `/machine enter` y `/machine off`. Solo donde el administrador te dio una cuenta.
- `equipo`: dejarle una tarea a otro de tus bots en un tablero de Gitea y ver las que te dejaron. Solo viaja el texto, y el administrador puede leerlo. Solo donde él lo configuró.
- `difusion`: tu canal de Telegram. El bot redacta los posts y vos los aprobás desde tu chat con `/publicar NÚMERO CÓDIGO` (el código te llega solo a vos); recién entonces salen. Solo donde el administrador configuró el canal.

Para ver la lista: `/settings packs`. Para prender uno: `/settings packs on NOMBRE`. Para apagarlo: `/settings packs off NOMBRE`. Se aplica en la próxima conversación, o sea con `/new`.

Menos grupos prendidos lo hace más liviano y rápido. Prendé solo lo que usás.

## 3. Comandos

Las palabras de los argumentos se pueden escribir en español, inglés o ruso. Los nombres anteriores — /estado, /dormir, /idioma, /voz, /avisos, /opinion, /compartir, /trabajos, /parar, /retomar, /archivos, /paquetes, /paquete — siguen funcionando.

**En el menú «/»**

- `/new`: empieza una conversación nueva. Tus memorias quedan.
- `/stop`: frena la respuesta actual.
- `/sleep`: se apaga de verdad. Si hay trabajo, te pregunta: `/sleep now` (también `ya`), `/sleep later` (`luego`) o `/sleep cancel` (`cancelar`).
- `/health`: qué anda ahora y dónde corre cada cosa.
- `/settings`: tus preferencias (ver abajo).
- `/manual [full]`: este manual, en el chat.
- `/feedback`: todo lo que le pedís al sistema para que mejore (ver más abajo).
- `/help`: la ayuda.

**Ajustes: `/settings`**

- `/settings`: muestra idioma, voz, avisos y el nivel de feedback.
- `/settings language es|ru|en|auto`: en qué idioma te contesta.
- `/settings voice [nombre]`: con qué voz te manda los audios.
- `/settings alerts daily|new|off`: avisos de ofertas de trabajo.
- `/settings packs`: tus grupos activos. `/settings packs on NOMBRE` o `off NOMBRE`: prender o apagar uno.
- `/settings feedback none|usage|all`: qué compartís con el administrador (ver más abajo).

**Trabajos (fuera del menú)**

- `/jobs`: qué está corriendo ahora y cómo van los subtítulos.
- `/jobs stop [filtro]`: frena las descargas (`/jobs stop subs` solo subtítulos).
- `/jobs resume`: sigue con los subtítulos de los canales ya empezados.
- `/files TEXTO`: busca un archivo que mandaste o que se bajó, aunque ya no esté.

**De Hermes**

- `/btw PREGUNTA`: una pregunta al margen, sin cortar lo que está haciendo.
- `/retry`: vuelve a intentar con tu último mensaje.
- `/undo [N]`: deshace tus últimos N mensajes (1 si no decís cuántos).
- `/model`: elegir otro modelo para esta conversación.
- `/commands`: la lista completa de comandos (incluye muchos técnicos).

## 4. Tus claves

Algunos servicios piden una clave personal: una llave que te da cada servicio, casi siempre gratis. Cada persona consigue y paga las suyas.

- Las cargás en la página **Tus claves** o pidiéndole a Hermes que guarde tu clave de ese servicio.
- **Nunca pegues una clave en el chat.** Va en esa página.
- Solo tu Hermes la usa; el administrador no la usa ni la comparte.
- Podés borrarla cuando quieras.
- Si el administrador configuró una clave compartida, algunos modelos gratis pueden usarla cuando no cargaste una propia.

Sin claves opcionales todo anda igual, con menos extras. Para chatear hace falta al menos una clave de IA: la tuya o, donde el administrador la ofrece, una compartida del servidor. `/health` te muestra qué funciona ahora.

## 5. Qué comparte y con quién

**Con quién pasan tus mensajes**

- La empresa que corre el modelo de IA que te contesta procesa lo que le escribís. Con modelos gratis, algunos proveedores pueden guardar y usar lo que mandás para entrenar.
- Las notas de voz las convierte en texto un servicio de voz.
- Las fotos las describe primero otro modelo.

**Con el administrador: `/feedback data`**

Con `/feedback` solo ves tu nivel actual y las formas de cambiarlo. Podés cambiarlo cuando quieras (es lo mismo que `/settings feedback`):

- `/feedback data none` (en español `nada`): el administrador no mira cómo lo usás para mejorarlo, ni siquiera conteos. El servidor igual guarda los registros técnicos que necesita para funcionar, sin el texto de tus conversaciones.
- `/feedback data usage` (`uso`; el nivel por defecto): puede ver qué herramientas se usaron, cuántas veces, errores, tiempos y qué modelo contestó. Nunca el texto de tus mensajes ni el contenido de tus archivos.
- `/feedback data all` (`todo`): puede leer la conversación para encontrar qué falló, solo para mejorar el asistente. Las claves y los textos largos que parecen secretos se tapan en lo que lee.

Los niveles también se aceptan en inglés o ruso (`none|usage|all`, `ничего|использование|всё`). El administrador es quien maneja el servidor. Estos niveles son un acuerdo sobre qué mira, no una barrera técnica.

## 6. Cómo opinar

- Reaccioná con 👍 o 👎 a cualquier respuesta. La reacción cuenta como un voto para el modelo que contestó; el voto no incluye el texto de la respuesta.
- `/feedback TEXTO`: para contar con palabras qué anduvo bien o mal. Lo lee el administrador para mejorar el asistente.
- `/feedback private TEXTO`: queda solo en tu espacio; el administrador no lo lee ni lo recibe.

## 7. Cuando duerme

Si no lo usás durante unos 10 minutos, Hermes se duerme para ahorrar recursos de la máquina.

El primer mensaje después de dormir tarda unos 20 a 30 segundos. Es normal.

Con `/sleep` lo dormís vos, de verdad. Los comandos corren al instante aunque Hermes esté contestando: no esperan a que termine. Si dejaste prendida una ubicación en vivo de Telegram, no hace nada mientras duerme: conviene apagarla.

## 8. Límites

- Una revisión de archivos que no encuentra nada **no prueba que esté a salvo**: solo que no figura como amenaza conocida.
- Hermes tiene que decirte cuando no revisó algo. Si no lo dice, preguntale.
- Puede equivocarse. Verificá los datos importantes: plata, salud, temas legales.
- Corta una respuesta con `/stop`; las descargas, con `/jobs stop`.

Este manual: /manual, o pedile a Hermes «mandame el manual en PDF».
