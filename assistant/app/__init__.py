"""Die KI als App: eigenes Fenster statt Terminal (dieselbe KI darunter).

  controller - dieselbe Logik wie das Terminal, Ein-/Ausgabe als Ereignisse
  server     - lokaler Webserver (nur 127.0.0.1, mit Schluessel) fuer das Fenster
  launcher   - oeffnet das Fenster (Edge/Chrome im App-Modus) und beendet alles,
               wenn das Fenster geschlossen wird
  static/    - die Oberflaeche (HTML/CSS/JS, ohne Internet)
"""
