# Test algoritmo

## Intro
Para llevar a cabo estas pruebas se han empleado los ficheros flows.py y router_manager.py de Python, que gestionan los archivos JSON que simulan el estado de la red. Además, se ha almacenado en un JSON el estado de dichos archivos para verificar que el sistema funciona correctamente.

## Prueba 1 Primer flujo

Fichero json: networkxalgorithm/tests/flows_uso21r1r2.json

Como ya se observó anteriormente, el algoritmo siempre asigna primero el camino r2 → r1 antes que el camino r4 → r3 cuando ambos tienen el mismo coste. Se ha modificado el orden en el que se añaden los nodos al grafo, pero el comportamiento continúa siendo el mismo.

```json
{
    "flows": [
        {
            "_id": "1",
            "version": 1,
            "route": [
                "ru",
                "r2",
                "r1",
                "rg"
            ]
        }
    ],
    "inactive_routers": [],
    "router_utilization": {
        "r1": 0.00,
        "r2": 0.00,
        "r3": 0.00,
        "r4": 0.00
    }
}
```

## Prueba 2 Segundo flujo

Fichero json: networkxalgorithm/tests/flows_uso21r1r2.json

Con un único flujo, se incrementa la utilización de los routers r1 y r2 para verificar que el algoritmo selecciona la ruta r4 → r3, tal como se muestra en el siguiente JSON.

```json

{
    "flows": [
        {
            "_id": "1",
            "version": 1,
            "route": [
                "ru",
                "r2",
                "r1",
                "rg"
            ]
        },
        {
            "_id": "2",
            "version": 1,
            "route": [
                "ru",
                "r3",
                "r4",
                "rg"
            ]
        }
    ],
    "inactive_routers": [],
    "router_utilization": {
        "r1": 0.21,
        "r2": 0.21,
        "r3": 0.00,
        "r4": 0.00
    }
}

```

### Prueba 3 Sorpaso primer umbral

Se ha probado a crear un flujo cuando se supera el 80% de capacidad. Se envia el siguiente aviso. Se añade el flow4 que al tener todos al 84% se envia por la ruta r2→r1

![use80%](<Captura desde 2025-03-24 09-19-14.png>)

```json

{
    "flows": [
        {
            "_id": "1",
            "version": 1,
            "route": [
                "ru",
                "r2",
                "r1",
                "rg"
            ]
        },
        {
            "_id": "2",
            "version": 1,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "3",
            "version": 1,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "4",
            "version": 1,
            "route": [
                "ru",
                "r2",
                "r1",
                "rg"
            ]
        }
    ],
    "inactive_routers": [],
    "router_utilization": {
        "r1": 0.84,
        "r2": 0.84,
        "r3": 0.84,
        "r4": 0.84
    }
}

```

## Prueba 5 Caida de router

Partiendo de la prueba anterior, se pausa el router r1, entonces las rutas que contienen ese router son modificadas como vemos en el siguiente json

```json

{
    "flows": [
        {
            "_id": "1",
            "version": 2,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "2",
            "version": 1,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "3",
            "version": 1,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "4",
            "version": 2,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        }
    ],
    "inactive_routers": [
        "r1"
    ],
    "router_utilization": {
        "r1": 0.84,
        "r2": 0.84,
        "r3": 0.84,
        "r4": 0.84
    }
}

```

## Prueba 6 Sorpaso segundo umbral

Como se supera el 95% por el unico camino disponible, no se le asigna ruta.

![segundoumbral](<Captura desde 2025-03-24 11-12-42.png>)

```json

{
    "flows": [
        {
            "_id": "1",
            "version": 2,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "2",
            "version": 1,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "3",
            "version": 1,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "4",
            "version": 2,
            "route": [
                "ru",
                "r4",
                "r3",
                "rg"
            ]
        },
        {
            "_id": "5",
            "version": 1
        }
    ],
    "inactive_routers": [
        "r1"
    ],
    "router_utilization": {
        "r1": 0.84,
        "r2": 0.84,
        "r3": 1.0,
        "r4": 1.0
    }
}

```

