import math
import threading
from time import sleep
from enum import Enum, auto
from gpiozero import MCP3008, OutputDevice, LED,PWMLED
from flask import Flask, request, render_template_string
import RPi.GPIO as GPIO

app = Flask(__name__)
estado_actual = "DESACTIVADA"

# Configuración GPIO 
GPIO.setmode(GPIO.BCM)
FAN_PIN = 26
GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.output(FAN_PIN, GPIO.LOW)  # Apagado por defecto

HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Control del Ventilador</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: linear-gradient(to right, #2c3e50, #4ca1af);
            font-family: 'Segoe UI', sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }

        h1 {
            font-size: 3rem;
            color: #ffffff;
            margin-bottom: 50px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.4);
        }

        form {
            display: flex;
            gap: 60px;
        }

        button {
            padding: 18px 60px;
            font-size: 24px;
            font-weight: bold;
            border: none;
            border-radius: 50px;
            cursor: pointer;
            transition: all 0.3s ease-in-out;
            box-shadow: 0 6px 15px rgba(0,0,0,0.2);
            letter-spacing: 1px;
        }

        .on {
            background-color: #00b894;
            color: white;
        }

        .on:hover {
            background-color: #1dd1a1;
        }

        .off {
            background-color: #d63031;
            color: white;
        }

        .off:hover {
            background-color: #ff6b6b;
        }
    </style>
</head>
<body>
    <h1>Control del Ventilador</h1>
    <form method="POST">
        <button name="accion" value="activar" class="on">ON</button>
        <button name="accion" value="desactivar" class="off">OFF</button>
    </form>
</body>
</html>
"""


def activar_alarma():
    print(">>> Activando ventilador")
    GPIO.output(FAN_PIN, GPIO.HIGH)

def desactivar_alarma():
    print(">>> Desactivando ventilador")
    GPIO.output(FAN_PIN, GPIO.LOW)

@app.route("/", methods=["GET", "POST"])
def control():
    global estado_actual
    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "activar" and estado_actual == "DESACTIVADA":
            activar_alarma()
            estado_actual = "ACTIVADA"
        elif accion == "desactivar" and estado_actual == "ACTIVADA":
            desactivar_alarma()
            estado_actual = "DESACTIVADA"
    return render_template_string(HTML)

class SensorCO2:
    def __init__(self, canal_aire):
        self.canal_aire = canal_aire
        self.entrada_gas = MCP3008(canal_aire)

    def obtener_nivel_gas(self):
        voltaje_aire = self.entrada_gas.voltage
        return voltaje_aire

    
class SensorTemperatura:
    def __init__(self, canal_sensor):
        self.canal_sensor = canal_sensor
        self.entrada_ntc = MCP3008(canal_sensor)

    def obtener_voltaje_ntc(self):
        voltaje_medido = self.entrada_ntc.voltage
        return voltaje_medido

    """despejando T de la ecuacion R(T) = Roe^((B/T)-(B/To)) """
    def convertir_a_grados_celsius(self, voltaje_medido):
        resistencia_base = 4700
        constante_beta = 3950
        resistencia_termistor = (3.3 * 10000 / voltaje_medido) - 10000
        temp_kelvin = constante_beta / (math.log(resistencia_termistor / resistencia_base) + (constante_beta / 273.15))
        temperatura_celsius = temp_kelvin - 273.15
        return -temperatura_celsius 


class SensorHumedad:
    def __init__(self, canal_entrada):
        self.canal_entrada = canal_entrada
        self.entrada_analogica = MCP3008(canal_entrada)

    def obtener_lectura(self):
        salida_voltaje = self.entrada_analogica.voltage
        return salida_voltaje
    
    """
        y=mx+b => Humedad   = (1/s)V - Voffset/S
        ya que sensibiliad es S = Voltios/Humedad 
        HR=V/S- V/offset
        V = voltage del sensor 
        Voffset = voltage de referencia en condiciones especifcias 
        S = Sensibilidad 
        V/S = convierte voltage leido a valor prop a la humedad 
        V/offset = ajusta para la referencia 
     """
    def calcular_humedad_relativa(self, salida_voltaje):
        porcentaje_humedad = (salida_voltaje / 0.0175) - 0.5 / 0.0175
        return porcentaje_humedad
        

#usaremos auto() = función de la biblioteca estándar de Python que automáticamente asigna un valor entero a cada miembro del enum, comenzando desde 1.

#posibles estados del sistema 
class EstadoSistema(Enum):
    NORMAL = auto()
    ALTA_TEMPERATURA = auto()
    BAJA_HUMEDAD = auto()
    MALA_CALIDAD_AIRE = auto()

#posibles eventos que pueden modficar estado del sistema
class EventoSistema(Enum):
    SUBE_TEMPERATURA = auto()
    BAJA_TEMPERATURA = auto()
    SUBE_HUMEDAD = auto()
    DISMINUYE_HUMEDAD = auto()
    EMPEORA_AIRE = auto()
    MEJORA_AIRE = auto()


class ControladorInvernadero:
    def __init__(self, actuador_ventilador, actuador_bomba, led_indicador):
        self.estado = EstadoSistema.NORMAL
        self.actuador_ventilador = actuador_ventilador
        self.actuador_bomba = actuador_bomba
        self.led_indicador = led_indicador

    def procesar_evento(self, evento_actual):
        if evento_actual == EventoSistema.SUBE_TEMPERATURA:
            self.estado = EstadoSistema.ALTA_TEMPERATURA
            self.actuador_ventilador.on()
            print("ACTIVA EL VENTILADOR CON LA CONEXION WIFI")
        elif evento_actual == EventoSistema.BAJA_TEMPERATURA:
            self.estado = EstadoSistema.NORMAL
            self.actuador_ventilador.off()
            print("DESACTIVA EL VENTILADOR CON LA CONEXION WIFI")
        if evento_actual == EventoSistema.DISMINUYE_HUMEDAD:
            self.estado = EstadoSistema.BAJA_HUMEDAD
            self.actuador_bomba.on()
            print("ACTIVA LA BOMBA")
        elif evento_actual == EventoSistema.SUBE_HUMEDAD:
            self.estado = EstadoSistema.NORMAL
            self.actuador_bomba.off()
            print("DESACTIVA LA BOMBA")
        if evento_actual == EventoSistema.EMPEORA_AIRE:
            self.estado = EstadoSistema.MALA_CALIDAD_AIRE
            self.led_indicador.on()
        elif evento_actual == EventoSistema.MEJORA_AIRE:
            self.estado = EstadoSistema.NORMAL
            self.led_indicador.off()
            

def ejecutar_monitor():
    sensor_humedad = SensorHumedad(6)
    sensor_gas = SensorCO2(5)
    sensor_ntc = SensorTemperatura(3)

    led_alerta = OutputDevice(27)
    fan = LED(22)
    bomba = LED(25)
    ciclo = 1
    leds_co2 =  PWMLED(20)

    sistema = ControladorInvernadero(fan, bomba, led_alerta)

    try:
        while True:
            print(f"Lectura del invernadero en progreso, ciclo número: {ciclo}")
            volt_humedad = sensor_humedad.obtener_lectura()
            volt_gas = sensor_gas.obtener_nivel_gas()
            volt_temp = sensor_ntc.obtener_voltaje_ntc()

            print("Voltaje humedad: {:.2f} V".format(volt_humedad))
            print("Voltaje temperatura: {:.2f} V".format(volt_temp))
            print("\n")

            humedad = sensor_humedad.calcular_humedad_relativa(volt_humedad)
            temperatura = sensor_ntc.convertir_a_grados_celsius(volt_temp)
            

            print(f"Humedad relativa: {humedad} %")
            print(f"Temperatura ambiente: {temperatura}")

            print("\n\n")

            if  humedad < 65 or temperatura > 21:
                print("Se detectó una condición crítica. LED de alerta encendido.")
                led_alerta.on()
            else:
                print("Todo está en condiciones normales.")
                led_alerta.off()

            if humedad < 65:
                sistema.procesar_evento(EventoSistema.DISMINUYE_HUMEDAD)
            else:
                sistema.procesar_evento(EventoSistema.SUBE_HUMEDAD)

            if temperatura > 21:
                sistema.procesar_evento(EventoSistema.SUBE_TEMPERATURA)
            else:
                sistema.procesar_evento(EventoSistema.BAJA_TEMPERATURA)

            if volt_gas >= 0:
                sistema.procesar_evento(EventoSistema.EMPEORA_AIRE)
                print("Se detecta C02, encendemos LEDs")
                leds_co2.frequency = 2
                leds_co2.value = 0.5
            

            sleep(1)
            print("\n\n")
            ciclo += 1

    except KeyboardInterrupt:
        print("Proceso interrumpido. Finalizando monitoreo.")


if __name__ == "__main__":
    hilo_ejecucion = threading.Thread(target=ejecutar_monitor)
    hilo_ejecucion.daemon = True
    hilo_ejecucion.start()
    app.run(host="0.0.0.0", port=5000, debug=True)