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

### Opciones gratuitas

#### 1. ⭐ OpenRouter (empezá por acá)
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
3. Abrí **Cargar mis claves** (`/keys/` en la misma dirección).
4. Elegí el proveedor, **pegá la clave** y tocá guardar.
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

## Para la búsqueda de trabajo (si tu instancia la incluye)

El sistema de búsqueda de empleo usa **la misma clave** que cargaste arriba: no necesitás
otra. Lo único que te va a pedir Hermes es **tu CV** (adjuntalo en el chat como PDF) y
algunos datos de tu perfil. Pedile cosas como *"buscamos laburo de …"* o *"haceme el CV
en PDF"*.

---

## Cuidado de tu clave

- Es **tuya**: tu uso cuenta contra **tu** cupo, no el de otra persona.
- Si sospechás que alguien la vio, **revocala** en el sitio del proveedor (mismo link del
  paso 1) y generá una nueva.
- Tu clave y tus archivos se guardan **solo en tu instancia**. El texto que le mandás a la IA lo procesa el
  proveedor que elijas, según sus condiciones. Los planes gratuitos pueden usar esos datos para entrenar sus
  modelos: no mandes nada sensible con una clave gratuita.
