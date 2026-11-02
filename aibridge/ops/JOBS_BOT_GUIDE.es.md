# Armá tu bot de Telegram para buscar trabajo (instructivo simple)

Vas a buscar trabajo hablando con **tu propio bot de Telegram**: le pasás tu CV y qué tipo de trabajo querés, y te
ayuda a revisar ofertas, preparar tu CV y llevar el seguimiento de tus postulaciones.

Para dejarlo listo necesitamos **dos datos tuyos**. Lleva unos **5 minutos** y alcanza con tener Telegram en el celular.

> El bot es **solo tuyo**: responde únicamente a tu ID. Si otra persona lo encuentra, no le contesta.

---

## Paso 1 · Creá tu bot

1. En Telegram abrí <https://t.me/BotFather> (o buscá **@BotFather**, el que tiene la tilde azul).
2. Tocá **Start** y escribí `/newbot`.
3. Te pregunta el **nombre** del bot. Es el que vas a ver en tu lista de chats; poné el que quieras, por ejemplo `Mi buscador de trabajo`.
4. Después te pregunta el **usuario** del bot. Tiene que ser único, sin espacios ni tildes, y **terminar en `bot`**, por ejemplo `mi_trabajo_2026_bot`. Si ya está ocupado te avisa: probá con otro.
5. BotFather te manda un mensaje con el **token**. Se ve así:

   ```
   123456789:AA…(unos 33 caracteres más)
   ```

   Ese es solo un ejemplo; el tuyo es distinto. **Copialo completo.**

> **El token es la contraseña de tu bot.** Quien lo tenga puede escribir como si fuera tu bot. No lo publiques, no lo
> pongas en grupos ni lo muestres en capturas. Si se filtra, escribile a BotFather `/revoke`, elegí tu bot y te da uno nuevo.

## Paso 2 · Averiguá tu ID de Telegram

Es un número (por ejemplo `123456789`) con el que el bot sabe que sos vos. **No es tu teléfono ni tu @usuario.**

1. Abrí <https://t.me/userinfobot> (o buscá **@userinfobot**).
2. Tocá **Start**.
3. Te responde con una línea que dice `Id:` y un número. Copiá ese número.

## Paso 3 · Mandanos los dos datos

Mandanos por **mensaje privado** (no en un grupo), con este formato:

```
Token: (el del paso 1)
ID: (el del paso 2)
```

Nada más. Nosotros lo dejamos configurado y te avisamos cuando esté listo.

## Paso 4 · Cuando te avisemos, probalo

1. Abrí tu bot en Telegram (el link es `https://t.me/` seguido del usuario que elegiste en el paso 1).
2. Tocá **Start** y escribí «Hola».
3. La primera vez te va a hacer algunas preguntas (tu CV, qué puestos buscás, en qué zona, qué sueldo esperás). Respondé de a una; con eso arma tu perfil.

---

## Tu propia clave (cuando quieras)

Al principio tu bot funciona con una **clave de prueba compartida**, con cupo limitado: sirve para empezar. Cuando tengas un rato (2 minutos por clave, gratis y sin tarjeta), conviene sacar la tuya:

1. Abrí la página web de tu Hermes (la dirección y la contraseña te las pasamos aparte) y entrá a **Tus claves**.
2. Elegí **OpenRouter** o **DeepSeek gratis (Token Harbor)**, tocá **Sacar la clave ↗**, creá la cuenta, copiá la clave y pegala en el campo. Se prueba al instante.
3. Si querés que entienda tus **notas de voz**, sumá también la de **Groq**.

Las claves van **solo en esa página**, nunca por Telegram. El bot te lo va a recordar en su primer mensaje.

---

## Qué tenés que saber

- **El primer mensaje puede tardar hasta un par de minutos.** Cuando no lo usás un rato, el asistente «duerme» para ahorrar recursos y se despierta con tu mensaje. No hace falta escribir de nuevo: el mensaje no se pierde.
- **Podés escribirle cuando quieras**, con texto, fotos o archivos (por ejemplo tu CV en PDF o la captura de una oferta).
- **Para frenar una respuesta larga**, escribí `/stop`.
- **Avisos diarios:** si querés que te avise por su cuenta cuando aparezcan ofertas nuevas, escribile `/avisos` y elegí cómo (uno por día, solo cuando haya algo, o ninguno). Por defecto no te manda nada hasta que lo pidas.
- Lo que le contás de tu carrera (CV, sueldo, etc.) queda guardado solo en tu instancia.

## Si algo no anda

| Qué pasó | Qué hacer |
|---|---|
| BotFather no acepta el usuario | Está ocupado o no termina en `bot`. Probá con otro. |
| El bot no contesta después de 3 o 4 minutos | Escribile de nuevo. Si sigue igual, avisanos. |
| El bot no contesta nunca | Lo más común es que el ID esté mal. Repetí el paso 2 y mandanos el número que te dio **@userinfobot**. |
| Mandé el token por error a otro lado | Escribile `/revoke` a BotFather, elegí tu bot y mandanos el token nuevo. |
| Quiero cambiarle el nombre o la foto | En BotFather: `/setname` y `/setuserpic`. No afecta nada de lo demás. |
