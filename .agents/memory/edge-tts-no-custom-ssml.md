---
name: edge-tts free endpoint blocks custom SSML
description: Microsoft's free/unofficial edge-tts backend rejects injected <break>/<emphasis> tags -- use sentence-split + concatenation for pauses instead.
---

`edge_tts.Communicate` builds `<speak><voice><prosody>{escaped_text}</prosody></voice></speak>`
and XML-escapes whatever text you pass in, so typing literal `<break/>` /
`<emphasis>` tags as plain text just gets escaped and does nothing.

It's technically possible to bypass the escaping by overwriting the public
`Communicate.texts` attribute (a generator the library's own `stream()` loop
reads from) with a pre-built raw SSML fragment. This is NOT a library
limitation -- the actual Microsoft backend was confirmed (via direct testing)
to reject any request whose SSML contains extra tags like `<break>` inside
`<prosody>`: the response comes back with zero audio bytes
(`NoAudioReceived`), even for something as minimal as a single bare
`<break time="300ms"/>`. This is almost certainly anti-abuse/signature
validation on Microsoft's side, not something fixable client-side.

**Why it matters:** any "add SSML support" ask for this pipeline cannot be
done via injected markup, no matter how it's wired in.

**How to apply:** for natural inter-sentence pauses, split text into
sentences with a plain-text splitter, generate each sentence as a normal
(plain, already-working) Edge-TTS request, then concatenate the resulting
audio clips with a short generated silence gap (ffmpeg `anullsrc` +
`concat` filter) between them. This gives real pauses without ever touching
the SSML the backend receives. Word-level emphasis has no safe equivalent
this way and had to be dropped as a feature.
