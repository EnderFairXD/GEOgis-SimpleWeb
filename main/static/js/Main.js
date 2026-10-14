document.addEventListener('DOMContentLoaded', function () {
    const datos = JSON.parse(document.getElementById('datos-jugadores').textContent);

    const mapa = L.map('mi_mapa').setView([40, 0], 4);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; colaboradores de OpenStreetMap'
    }).addTo(mapa);

    // Solo se puede arrastrar: dibujar, editar o borrar no se guardaría en el servidor.
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

    const modal = new bootstrap.Modal(document.getElementById('jugadorModal'));

    function leerCookie(nombre) {
        const par = document.cookie.split('; ').find(function (c) { return c.startsWith(nombre + '='); });
        return par ? decodeURIComponent(par.split('=')[1]) : '';
    }

    function guardarUbicacion(id, latlng) {
        const punto = latlng.wrap(); // por si se arrastra más allá de ±180° de longitud
        return fetch('/api/jugadores/' + id + '/ubicacion/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': leerCookie('csrftoken')
            },
            body: JSON.stringify({ lat: punto.lat, lng: punto.lng })
        }).then(function (respuesta) {
            if (!respuesta.ok) {
                throw new Error('El servidor respondió ' + respuesta.status);
            }
            return respuesta.json();
        });
    }

    function mostrarFicha(propiedades) {
        document.getElementById('modalAlias').innerText = propiedades.alias;
        document.getElementById('modalNombre').innerText = 'Nombre real: ' + propiedades.nombre;
        document.getElementById('modalPlataforma').innerText = propiedades.plataforma;

        const lista = document.getElementById('modalListaJuegos');
        lista.innerHTML = '';

        const juegos = propiedades.historial_juegos || [];
        if (juegos.length === 0) {
            const vacio = document.createElement('li');
            vacio.className = 'list-group-item text-muted';
            vacio.textContent = 'Sin puntuaciones registradas';
            lista.appendChild(vacio);
        } else {
            juegos.forEach(function (juego) {
                const li = document.createElement('li');
                li.className = 'list-group-item d-flex justify-content-between align-items-center';
                // textContent evita inyectar HTML con nombres de juego raros
                const titulo = document.createElement('span');
                titulo.textContent = juego.titulo;
                const puntos = document.createElement('span');
                puntos.className = 'badge bg-primary rounded-pill';
                puntos.textContent = juego.puntos + ' pts';
                li.appendChild(titulo);
                li.appendChild(puntos);
                lista.appendChild(li);
            });
        }
        modal.show();
    }

    L.geoJSON(datos, {
        onEachFeature: function (feature, layer) {
            layer.on('click', function () {
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
    }).addTo(mapa);
});
