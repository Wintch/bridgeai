# Shared starter key notice (job-search)

## Shared starter key (only when `/workdir/.starter-key` exists)

Only a stack of the operator's own account starts on the operator's key (the file is the marker; `provision_stack.sh`
writes it only with `--operator-account`). It has a quota shared with other stacks and the operator can change or cut it. Tell the person **once**, in their language, at the end of your
first reply (after answering what they asked; do not delay the onboarding for it):

- Check `/workdir/.starter-key-told`. If it exists, say nothing. Otherwise add the note below and run
  `touch /workdir/.starter-key-told`.
- es: "Un aviso: por ahora uso una clave de prueba compartida, con cupo limitado, y el administrador puede cambiarla o
  cortarla; si un día dejo de contestar, puede ser eso. Para tener la tuya (gratis, 2 minutos): entrá a la página web de
  tu Hermes (la dirección que te pasó el administrador), abrí «Tus claves», tocá «Sacar la clave» en OpenRouter o en
  DeepSeek gratis (Token Harbor) y pegala ahí. Con Groq también entiendo tus notas de voz. Las claves van solo en esa
  página: nunca me las pases por acá."
- ru: "Небольшое предупреждение: сейчас я работаю на общем пробном ключе с ограниченным лимитом, и администратор может
  его заменить или отключить; если однажды я перестану отвечать, возможно, дело в этом. Чтобы получить свой ключ
  (бесплатно, 2 минуты): откройте веб-страницу вашего Hermes (адрес вам дал администратор), раздел «Tus claves» (страница на испанском), нажмите
  «Sacar la clave» (получить ключ) у OpenRouter или DeepSeek бесплатно (Token Harbor) и вставьте его там. С Groq я пойму и ваши голосовые.
  Ключи вводятся только на этой странице: никогда не присылайте их мне в чат."
- en: "A heads-up: for now I run on a shared trial key with a limited quota, and the administrator can change or cut it;
  if I ever stop answering, that may be why. To get your own (free, 2 minutes): open your Hermes web page (the address
  the administrator gave you), go to «Tus claves» (the page is in Spanish), press «Sacar la clave» (get the key) for OpenRouter or free DeepSeek (Token Harbor) and
  paste it there. With Groq I also understand your voice notes. Keys go only on that page: never send them to me here."
- If the person says they already added a key of their own, or asks you to stop mentioning it: `rm -f
  /workdir/.starter-key` (the web banner goes with the next welcome refresh). Never ask for the key in the chat.
