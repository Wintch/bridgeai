# Cómo conseguir tus claves de IA (guía para usuarios nuevos)

Tu asistente **Hermes** necesita una **clave de IA propia**. Es como una contraseña
que le da permiso para usar un modelo de inteligencia artificial en tu nombre.
Alcanza con **una sola**. Empezá por la primera opción y bajá por la lista solo si
esa no te funciona: están ordenadas **de lo más simple a lo más complejo**, y al final
van las opciones **pagas**.

> Regla de oro: la clave es **tuya y secreta**. No se la pases a nadie, no la mandes
> por chat ni por mail. La pegás una sola vez en tu página de claves (paso 2) y listo.

---

## Paso 1 · Conseguí una clave

### Recomendadas (empezá por acá)

En la página de claves cada servicio tiene un botón **Sacar la clave ↗** que abre el sitio correcto, y al lado el
campo para pegarla.

#### ⭐ DeepSeek gratis (Token Harbor)
- **Costo:** gratis, sin tarjeta. Es el modelo mejor puntuado en este sistema, con tu propio cupo.
- **El cupo gratis es semanal:** si se agota, Hermes usa otros modelos hasta que vuelve, y la página de claves muestra
  la fecha en que vuelve.
- **Ojo:** con sus modelos gratis, Token Harbor puede guardar lo que le mandás y usarlo para entrenar. No mandes nada
  sensible por ahí.

#### ⭐ Notas de voz (Groq)
- **Costo:** gratis, sin tarjeta. No sirve para chatear: hace que tus audios (por Telegram o como archivo) se
  entiendan aunque las computadoras de casa estén apagadas.

### Más opciones gratuitas

#### 1. OpenRouter
- **Costo:** gratis, sin tarjeta. Tiene modelos gratuitos (los que terminan en `:free`) con límite diario.
- **Dónde:** <https://openrouter.ai/settings/keys>
- **Cómo:** creá cuenta → **Create Key** → copiala. **Empieza con `sk-or-`**.

#### 2. Google Gemini
- **Costo:** gratis con cupo diario bajo; alcanza para probar.
- **Dónde:** <https://aistudio.google.com/apikey>
- **Cómo:** iniciá sesión con tu cuenta de Google → **Create API key** → copiala. **Empieza con `AIza`**.

#### 3. Hugging Face
- **Costo:** créditos mensuales gratuitos de inferencia.
- **Dónde:** <https://huggingface.co/settings/tokens>
- **Cómo:** creá cuenta → **New token** (tipo *Read* alcanza) → copiala. **Empieza con `hf_`**.

#### 4. NVIDIA NIM (la más generosa, pero con más pasos)
- **Costo:** gratis, sin tarjeta. Alrededor de 40 pedidos por minuto.
- **Requisitos:** un mail y **un celular propio para validar el teléfono** (código por SMS).
  Si no podés validar un teléfono, usá una de las opciones de arriba.
- **Dónde:** <https://build.nvidia.com/settings/api-keys>
- **Cómo:**
  1. Entrá y creá cuenta o iniciá sesión con tu mail (te va a pedir verificar el mail y **validar tu número de teléfono**: es obligatorio, tené el celular a mano para recibir el código por SMS).
  2. Tocá **Generate API Key** (si pide nombre, poné cualquiera, por ejemplo `hermes`).
  3. Copiá la clave **completa**. **Empieza con `nvapi-`**. Se muestra una sola vez: copiala ya.

| # | Proveedor | Empieza con | Gratis | Dificultad |
|---|---|---|---|---|
| 1 | OpenRouter | `sk-or-` | Modelos `:free`, cupo diario | Muy simple |
| 2 | Google Gemini | `AIza` | Cupo diario bajo | Simple |
| 3 | Hugging Face | `hf_` | Créditos mensuales | Simple |
| 4 | NVIDIA NIM | `nvapi-` | Sí, sin tarjeta | Más pasos: pide validar teléfono |

> Si algún proveedor no está disponible en tu país o no te deja registrarte, pasá al
> siguiente de la lista: cualquiera sirve.

### Opciones pagas (solo si lo gratis no te alcanza)

Se usan cuando llegás seguido al límite diario de las gratuitas o querés modelos más potentes.
**Cargá saldo vos mismo y ponele un tope de gasto en el sitio del proveedor.**

- **OpenRouter con crédito:** es **la misma clave** `sk-or-` de la opción 1. Cargás saldo
  en <https://openrouter.ai/settings/credits> y se desbloquean más modelos y límites
  mucho más altos. No tenés que cambiar nada en tu instancia.
- Otros proveedores pagos (por ejemplo OpenAI o Anthropic) **no se cargan desde la página
  de claves**. Si querés usar uno, pedíselo a quien administra tu instancia.

---

## Paso 2 · Cargala en tu instancia

1. Abrí tu página de Hermes (la dirección que te pasamos, por ejemplo `https://tunombre.…`).
2. Entrá con el usuario y contraseña que te dimos.
3. Abrí **Tus claves** (`/keys/` en la misma dirección).
4. Buscá el servicio, tocá **Sacar la clave ↗** si todavía no la tenés, **pegá la clave** y tocá guardar.
   Se valida al instante contra el proveedor y **recién ahí se guarda**.
5. La página elige un modelo que funcione con tu clave y empieza a usarlo. Si preferís otro,
   usá **«Cambiar de modelo»** en esa misma página; podés cambiarlo cuando quieras.
   Si el modelo que eligió la página no funciona con tu clave, te muestra una lista: elegí uno y tocá
   **«Usar este modelo»** (tu clave sigue en el cuadro, así que se guarda junto con ese modelo).

### Si la página rechaza tu clave
- Revisá que la copiaste **completa**, **sin espacios** al principio o al final.
- Verificá que empiece como dice la tabla de arriba.
- Si dice que el proveedor está **limitando el uso** (error 429), tu clave **es válida** y la página la guardó, pero no
  cambió el modelo. Los límites gratuitos suelen renovarse al día siguiente (los modelos gratuitos de OpenRouter
  comparten un cupo diario chico): probá **«Cambiar de modelo»** más tarde, o cargá la clave de otro proveedor.
  Esperar un minuto no alcanza.
- Si la clave venció o la revocaste, generá otra y repetí el paso 2.

---

## Telegram (opcional)

En la misma página hay una tarjeta **Telegram**: creás tu bot con @BotFather, averiguás tu ID con @userinfobot, pegás
los dos y listo, Hermes te contesta por Telegram (texto, audios, fotos). El bot es solo tuyo: no le contesta a nadie
más. Si dice «Telegram lo conectó el administrador», ya está hecho y no tenés que tocar nada.

---

## Para la búsqueda de trabajo (si tu instancia la incluye)

El sistema de búsqueda de empleo usa **la misma clave** que cargaste arriba: no necesitás
otra. Lo único que te va a pedir Hermes es **tu CV** (adjuntalo en el chat como PDF) y
algunos datos de tu perfil. Pedile cosas como *"buscamos laburo de …"* o *"haceme el CV
en PDF"*.

---

## Paso 3 · Servicios opcionales (solo si los querés)

Hermes ya sabe **sin ninguna clave extra**: mapas y recorridos, clima con dos modelos meteorológicos, dólar, feriados,
inflación, Wikipedia, aviones que pasan por arriba y titulares de noticias. Algunas cosas mejoran con una clave
**tuya, gratis, que se saca solo con email y sin tarjeta**. Si no te interesan, ignorá esta parte: nada deja de andar.

| Servicio | Qué suma con tu clave | Sin clave | Dónde se saca |
|---|---|---|---|
| **Mapas (Geoapify)** | búsquedas de lugares más precisas y mapas con más cupo | anda igual con OpenStreetMap | <https://myprojects.geoapify.com> → registrate con email → creá un proyecto → copiá la *API key* |
| **Películas y series (TMDB)** | qué hay en cartelera y en qué plataforma se ve cada película o serie en Argentina | solo el resumen de Wikipedia | <https://www.themoviedb.org/settings/api> → creá cuenta con email → pedí una clave de uso personal |
| **Mapas más prolijos (CARTO)** | los mapas salen en el estilo claro de CARTO, sin depender de los tiles de OpenStreetMap | se dibujan igual con OpenStreetMap | <https://carto.com/basemaps/apikey/> → pedila en el formulario (gratis, sin cuenta ni tarjeta) y copiá la clave. Es solo tuya: los [términos de CARTO](https://carto.com/legal/basemap-terms/) no permiten usar la de otra persona. Cada mapa lleva «© OpenStreetMap contributors, © CARTO». |

- **Dónde se carga:** en esta misma página de claves, en la sección **Servicios opcionales**. Se comprueba con el
  servicio antes de guardarse y nunca pasa por el chat. Si tu Hermes no tiene página de claves, pasásela al
  administrador.
- **Si alguna vez te hace falta una**, Hermes te lo dice **una sola vez**, en una frase, con el link. Si no te
  interesa, decíselo y no vuelve a sugerirlo.
- En `/estado` ves qué servicios tenés activos.
- **Si un sitio te pide tarjeta, no la pongas:** ninguno de estos la necesita. Si la pide, avisá y lo sacamos de la lista.

---

## Cuidado de tu clave

- Es **tuya**: tu uso cuenta contra **tu** cupo, no el de otra persona.
- Si sospechás que alguien la vio, **revocala** en el sitio del proveedor (mismo link del
  paso 1) y generá una nueva.
- Tu clave y tus archivos se guardan **solo en tu instancia**. El texto que le mandás a la IA lo procesa el
  proveedor que elijas, según sus condiciones. Los planes gratuitos pueden usar esos datos para entrenar sus
  modelos: no mandes nada sensible con una clave gratuita.
