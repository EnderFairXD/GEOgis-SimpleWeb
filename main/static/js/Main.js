document.addEventListener('DOMContentLoaded', function () {
    const elementoMapa = document.getElementById('mi_mapa');
    // El modo arrastrar solo se ofrece a quien puede guardar cambios (el servidor lo comprueba igualmente).
    const puedeEditar = elementoMapa.dataset.puedeEditar === '1';

    const mapa = L.map(elementoMapa).setView([40, 0], 4);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; colaboradores de OpenStreetMap',
        // OpenStreetMap bloquea las teselas pedidas sin Referer, y Django por defecto no lo envía
        // a otros dominios (Referrer-Policy: same-origin). Aquí se manda solo el origen de la web.
        referrerPolicy: 'strict-origin-when-cross-origin'
    }).addTo(mapa);

    // Solo se puede arrastrar: dibujar, editar o borrar no se guardaría en el servidor.
    if (puedeEditar) {
        mapa.pm.addControls({
            position: 'topleft',
            drawMarker: false,
            drawPolyline: false,
            drawPolygon: false,
            drawCircle: false,
            drawCircleMarker: false,
            drawRectangle: false,
            drawText: false,
            cutPolygon: false,
            editMode: false,
            dragMode: true,
            removalMode: false,
            rotateMode: false
        });
    }

    const modal = new bootstrap.Modal(document.getElementById('jugadorModal'));
    const selectorRadio = document.getElementById('modalRadio');
    const listaCercanos = document.getElementById('modalCercanos');
    let fichaActual = null; // id del jugador cuya ficha está abierta

    function leerCookie(nombre) {
        const par = document.cookie.split('; ').find(function (c) { return c.startsWith(nombre + '='); });
        return par ? decodeURIComponent(par.split('=')[1]) : '';
    }

    function pedirJson(url, opciones) {
        return fetch(url, opciones).then(function (respuesta) {
            if (!respuesta.ok) {
                throw new Error('El servidor respondió ' + respuesta.status);
            }
            return respuesta.json();
        });
    }

    function guardarUbicacion(id, latlng) {
        const punto = latlng.wrap(); // por si se arrastra más allá de ±180° de longitud
        return pedirJson('/api/jugadores/' + id + '/ubicacion/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': leerCookie('csrftoken')
            },
            body: JSON.stringify({ lat: punto.lat, lng: punto.lng })
        });
    }

    // Elemento de lista con un texto y, opcionalmente, una insignia a la derecha.
    // textContent evita inyectar HTML con nombres raros.
    function elementoLista(texto, insignia, clases) {
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center ' + (clases || '');
        const titulo = document.createElement('span');
        titulo.textContent = texto;
        li.appendChild(titulo);
        if (insignia) {
            const valor = document.createElement('span');
            valor.className = 'badge bg-primary rounded-pill';
            valor.textContent = insignia;
            li.appendChild(valor);
        }
        return li;
    }

    function rellenarLista(lista, elementos, textoVacio) {
        lista.replaceChildren();
        if (elementos.length === 0) {
            lista.appendChild(elementoLista(textoVacio, null, 'text-muted'));
        }
        elementos.forEach(function (elemento) { lista.appendChild(elemento); });
    }

    function cargarCercanos() {
        const id = fichaActual;
        const km = selectorRadio.value;
        rellenarLista(listaCercanos, [], 'Buscando…');

        pedirJson('/api/jugadores/' + id + '/cercanos/?km=' + km).then(function (datos) {
            // Si mientras tanto se abrió otra ficha o se cambió el radio, esta respuesta ya no vale.
            if (id !== fichaActual || km !== selectorRadio.value) return;
            rellenarLista(listaCercanos, datos.cercanos.map(function (cercano) {
                return elementoLista(cercano.alias, Math.round(cercano.distancia_km) + ' km');
            }), 'Nadie en ese radio');
        }).catch(function (error) {
            console.error('No se pudieron cargar los jugadores cercanos:', error);
            rellenarLista(listaCercanos, [], 'No se pudieron cargar los jugadores cercanos');
        });
    }

    function mostrarFicha(propiedades) {
        fichaActual = propiedades.id;
        document.getElementById('modalAlias').innerText = propiedades.alias;
        document.getElementById('modalNombre').innerText = 'Nombre real: ' + propiedades.nombre;
        document.getElementById('modalPlataforma').innerText = propiedades.plataforma;

        rellenarLista(
            document.getElementById('modalListaJuegos'),
            (propiedades.historial_juegos || []).map(function (juego) {
                return elementoLista(juego.titulo, juego.puntos + ' pts');
            }),
            'Sin puntuaciones registradas'
        );
        cargarCercanos();
        modal.show();
    }

    selectorRadio.addEventListener('change', cargarCercanos);

    function pintarJugadores(datos) {
        const capaJugadores = L.geoJSON(datos, {
            onEachFeature: function (feature, layer) {
                layer.on('click', function () {
                    // Al soltar un marcador arrastrado llega también un clic: no abre la ficha.
                    if (layer.pm && layer.pm.dragging()) return;
                    mostrarFicha(feature.properties);
                });

                // Fin del arrastre (modo "arrastrar" de Geoman): se guarda la nueva posición.
                layer.on('pm:dragend', function (evento) {
                    const marcador = evento.layer || layer;
                    guardarUbicacion(feature.properties.id, marcador.getLatLng()).catch(function (error) {
                        console.error('No se pudo guardar la ubicación:', error);
                        alert('No se pudo guardar la nueva ubicación. Recarga la página para ver la posición real.');
                    });
                });
            }
        });

        // Los marcadores cercanos se agrupan en un círculo con el número de jugadores.
        const grupos = L.markerClusterGroup();
        grupos.addLayer(capaJugadores);
        mapa.addLayer(grupos);

        // En modo arrastrar se desagrupan para poder mover cada marcador;
        // al salir se vuelven a agrupar con las posiciones nuevas.
        mapa.on('pm:globaldragmodetoggled', function (evento) {
            if (evento.enabled) {
                mapa.removeLayer(grupos);
                capaJugadores.addTo(mapa);
            } else {
                mapa.removeLayer(capaJugadores);
                grupos.clearLayers();
                grupos.addLayer(capaJugadores);
                mapa.addLayer(grupos);
            }
        });

        // Encuadra el mapa en los jugadores; si no hay ninguno se queda la vista inicial.
        if (capaJugadores.getLayers().length > 0) {
            mapa.fitBounds(capaJugadores.getBounds(), { padding: [40, 40], maxZoom: 8 });
        }
    }

    pedirJson(elementoMapa.dataset.urlJugadores).then(pintarJugadores).catch(function (error) {
        console.error('No se pudieron cargar los jugadores:', error);
        alert('No se pudieron cargar los jugadores. Prueba a recargar la página.');
    });
});
