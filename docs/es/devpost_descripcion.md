[English](../devpost_description.md) | [Español](devpost_descripcion.md)

# CourtFatigue — texto para Devpost

> Pensado para jueces no técnicos: el lenguaje evita estadística avanzada.

## Título
CourtFatigue: el problema no es cuándo sale un jugador, sino cómo entra

## Descripción corta (tagline)
En sus primeros 30 segundos en cancha los jugadores de la NBA tiran peor, eso le cuesta a cada equipo unos 27 puntos por temporada, y se confirmó en una prueba preregistrada en una temporada que nuestro modelo nunca vio. La "fatiga de tiro" que temen los entrenadores no aparece.

## Inspiración
Los entrenadores sacan a los jugadores para que descansen, suponiendo que el tiro se viene abajo al final de un tramo largo. Queríamos saber si es cierto, y dónde más lo nota la cancha.

## Qué hace
CourtFatigue mide cómo cambia el tiro de un jugador de la NBA con el tiempo en cancha, descontando la dificultad de cada tiro. El titular es lo contrario del mito:

- **Arranque en frío:** los jugadores tiran **1.46 puntos porcentuales peor en sus primeros 30 segundos** tras entrar (IC 95% −1.95 a −0.97), y se normaliza hacia el minuto 2. Le cuesta a cada equipo unos **27 puntos por temporada** (IC 19 a 36), cerca de 0.9 victorias. Preregistramos una prueba en la temporada 2025-26, que el análisis nunca vio, y se **replicó: −1.35 pp, IC 95% −2.24 a −0.46**.
- **Dónde duele:** la caída es 2-3 veces mayor en triples (−1.8) y media distancia (−2.6) que cerca del aro (−0.8). Aparece incluso en los tiros libres (−1.9), donde no hay defensor. Y no crece con el tiempo en el banquillo: es entrar al ritmo del partido, no enfriarse.
- **Sin fatiga de tiro** hasta ~12 minutos seguidos (+0.21 pp, IC 95% −0.13 a +0.56), también en 2025-26 (+0.31). 0 de 592 jugadores muestran una caída demostrable.
- **Partidos en días seguidos** cuestan 0.39 pp (unos 12 puntos por temporada); **jugar en casa** suma 0.38 pp.

| Hallazgo | Acción para el entrenador |
| --- | --- |
| Arranque en frío: −1.46 pp en los primeros 30 s, ~27 puntos por temporada | Primera jugada tras un cambio: un corte o una penetración para el que entra, no su primer triple. Activar al suplente antes de que entre, aunque haya descansado poco. |
| Sin fatiga de tiro hasta ~12 min seguidos | No sacar al mejor tirador solo por miedo al cansancio. |
| Partidos en días seguidos: −0.39 pp | Repartir minutos en el segundo partido. |

El cuerpo técnico tiene una ficha de una página, una calculadora para el banquillo, una auditoría por equipo y un simulador 3D donde cada término está medido en datos.

## Cómo lo construimos
872,158 tiros de 4,920 partidos (2021-22 a 2024-25), más 219,156 tiros de 2025-26 para la replicación. Reconstrucción de los tramos en cancha desde el play-by-play, un modelo de tiro esperado (gradient boosting) validado por partidos y por temporada, efectos fijos por jugador-temporada con errores agrupados, corrección de Benjamini-Hochberg, bootstrap por partidos y una prueba placebo. Web estática bilingüe (HTML/CSS/JS, sin librerías) y un simulador con Three.js.

## Por qué importa la estadística
Una regla ingenua ("sustituir cuando el acierto cae 3 puntos") marca al 60.5% de los jugadores, y sigue marcando al 59.4% cuando los minutos se barajan al azar, donde la fatiga no puede existir. La nuestra marca 0%. La mayoría de los "está cansado" son ruido.

Además publicamos en un commit el plan de la replicación, las estimaciones congeladas y la regla de éxito **antes** de descargar 2025-26. El resultado podía fallar; no falló.

## Dificultades
El play-by-play no registra las sustituciones entre cuartos, así que inferimos quién seguía en cancha. El play-by-play de 2025-26 venía en otro formato: escribimos un adaptador y lo validamos en 2024-25, donde existen los dos formatos (coincide en el 99.66% de los tiros).

Los entrenadores también sacan a quien ven cansado, lo que puede esconder fatiga. En los tramos que terminaron por razones ajenas al entrenador (medio tiempo, fin del partido, problemas de faltas) no hay caída (+0.83 pp). En los que corta el entrenador, los tiros de los últimos 2 minutos antes del cambio están 9 puntos por debajo de lo normal: el entrenador reacciona a los fallos recientes, no a los minutos jugados.

## Limitaciones
Asociación, no causalidad. Sin datos de seguimiento ni biométricos. A nivel individual solo se detectan caídas de unos 14 pp o más. Casi no hay tiros tras ~12 minutos seguidos. Los 27 puntos son el costo total del arranque en frío; cuánto puede recuperar un entrenador no se ha probado, y los equipos no se diferencian entre sí más allá del ruido. En 2025-26 las ventanas de 30-60 s y 1-2 min no se distinguieron de cero: el efecto se concentra en los primeros 30 segundos.

## Próximos pasos
Datos de seguimiento con la posición de los defensores en las temporadas recientes, carga acumulada por viajes y efectos defensivos de la fatiga.

## Uso de IA
Usamos un asistente de programación con IA para ayudar a escribir código y textos. Las preguntas, las decisiones del análisis y la ejecución final son nuestras.
