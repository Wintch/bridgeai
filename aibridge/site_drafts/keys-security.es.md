<!-- Draft for the public website, keys section. For operator review; not yet in the site repo.
     Items marked "(planeado)" (planned in the English draft) must stay labelled until they are live. -->

# Tus claves son tuyas

**La cuenta y la clave son tuyas.** Creás tu cuenta con cada proveedor de IA (NVIDIA, OpenRouter, Gemini, Groq...), aceptás
sus términos y pegás tu propia clave en tu propio asistente. Si lo que hacés con esa clave cuenta como prueba o como
producción lo definen los términos del proveedor: es un tema entre vos y él.

**Nosotros ponemos el software y el lugar donde corre, no las claves.** No te damos claves, no las revendemos y nadie nos
paga por acceso a modelos. Nuestra regla es que una clave nunca se comparte entre cuentas. (Algunas instalaciones viejas
arrancaron con una clave de prueba compartida y temporal; la estamos retirando, y si la tuya fue así, el mensaje de bienvenida
lo dice.)

## Lo que hacemos

- La clave se pega solo en **tu página de claves**, nunca en el chat. **Nunca te la pedimos** por chat, mail ni mensaje.
- Se **verifica con el proveedor cuando la pegás**, y de ahí en adelante la página de claves solo muestra los **últimos 4
  caracteres**.
- Esa copia vive en tu instancia, para que el asistente pueda llamar al proveedor en tu nombre. Nuestros propios controles
  también la usan para comprobar que sigue funcionando.
- Estamos trabajando para que las claves no queden en copias de seguridad, registros ni exportaciones, y para que ninguna
  cuenta use la clave de otra (ver «Hacia dónde vamos»). Cada punto se revisa con pruebas antes de afirmarlo.

## Lo que te pedimos a vos

- **Poné un límite de gasto** en el proveedor antes de pegar una clave paga, por un monto que puedas perder, y activá la
  alerta de uso. Es la protección que sigue funcionando aunque algo falle de nuestro lado.
- **Una clave por app o bot.** No reutilices una que uses en otro lado.
- **Revocala y generá otra** si sospechás una filtración, o si la pegaste en un chat por error.
- **Avisanos**, así revisamos también nuestra parte.

## Los límites, sin vueltas

Para llamar al proveedor, un servicio en marcha tiene que tener la clave en memoria. Hoy la copia de trabajo de tu clave está
en tu instancia y la puede leer, técnicamente, quien administra el servidor y el propio proceso del asistente. Las copias de seguridad diarias del servidor también guardan
una copia unos días. Por eso el
tope de gasto del proveedor y la posibilidad de revocar rápido son tu red de seguridad real, más que cualquier promesa nuestra.

## Hacia dónde vamos

Una filtración de clave es de lo peor que nos puede pasar: se puede usar para cualquier cosa y, con proveedores pagos, gastar
plata real. Por eso el rumbo es que la clave quede del lado del cliente y que nosotros no seamos quienes la filtren:

1. **Primero (planeado, pasos chicos):** avisos y topes de gasto, copias de seguridad sin claves, nada de claves de reserva
   ajenas, y revisión de que ninguna cuenta comparta clave con otra.
2. **Siguiente (planeado):** que el asistente no tenga la clave en su contenedor: un componente aparte la guarda, llama al
   proveedor por él y aplica el tope. Cifrado en disco.
3. **Después (planeado):** una opción para que la clave quede cifrada con una contraseña que solo vos tenés, y alertas de uso
   anormal. Todavía falta diseñar el mecanismo seguro para cargarlas y mantenerlas; lo publicaremos cuando esté definido.

Si sospechás que una clave se filtró: revocala primero en el proveedor, después cargá la nueva y escribinos.
