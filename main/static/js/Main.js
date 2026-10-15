document.addEventListener('DOMContentLoaded', function () {
    const elementoMapa = document.getElementById('mi_mapa');
    // El modo arrastrar solo se ofrece a quien puede guardar cambios (el servidor lo comprueba igualmente).
    const puedeEditar = elementoMapa.dataset.puedeEditar === '1';

    const TIPOS = { FONDO: 'Fondo', INDUSTRIAL: 'Industrial', TRAFICO: 'Tráfico' };
    const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
    // Canarias queda lejos de la Península: cada zona tiene su propio encuadre.
    const VISTAS = {
        'Península y Baleares': [[35.2, -9.6], [43.9, 4.4]],
        'Canarias': [[27.6, -18.2], [29.5, -13.3]]
    };

    const mapa = L.map(elementoMapa).fitBounds(VISTAS['Península y Baleares']);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; colaboradores de OpenStreetMap | Datos: MITECO',
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

    // Botones para saltar entre la Península y Canarias.
    const controlVistas = L.control({ position: 'topright' });
    controlVistas.onAdd = function () {
        const caja = L.DomUtil.create('div', 'leaflet-bar control-vistas');
        Object.keys(VISTAS).forEach(function (nombre) {
            const boton = L.DomUtil.create('button', '', caja);
            boton.type = 'button';
            boton.textContent = nombre;
            L.DomEvent.on(boton, 'click', function (evento) {
                L.DomEvent.stop(evento);
                mapa.fitBounds(VISTAS[nombre]);
            });
        });
        L.DomEvent.disableClickPropagation(caja);
        return caja;
    };
    controlVistas.addTo(mapa);

    // Leyenda: el color del marcador indica el tipo de estación.
    const leyenda = L.control({ position: 'bottomleft' });
    leyenda.onAdd = function () {
        const caja = L.DomUtil.create('div', 'leyenda');
        Object.keys(TIPOS).forEach(function (tipo) {
            const fila = L.DomUtil.create('div', '', caja);
            L.DomUtil.create('span', 'punto estacion-' + tipo.toLowerCase(), fila);
            fila.appendChild(document.createTextNode(TIPOS[tipo]));
        });
        return caja;
    };
    leyenda.addTo(mapa);

    const modal = new bootstrap.Modal(document.getElementById('fichaModal'));
    const ficha = {
        nombre: document.getElementById('fichaNombre'),
        lugar: document.getElementById('fichaLugar'),
        cargando: document.getElementById('fichaCargando'),
        contenido: document.getElementById('fichaContenido'),
        contaminante: document.getElementById('fichaContaminante'),
        unidad: document.getElementById('fichaUnidad'),
        sinMediciones: document.getElementById('fichaSinMediciones'),
        notaPocosDatos: document.getElementById('fichaNotaPocosDatos'),
        radio: document.getElementById('fichaRadio'),
        cercanas: document.getElementById('fichaCercanas')
    };
    let fichaActual = null;    // id de la estación cuya ficha está abierta
    let detalleActual = null;  // datos de esa estación

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
        return pedirJson('/api/estaciones/' + id + '/ubicacion/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': leerCookie('csrftoken')
            },
            body: JSON.stringify({ lat: latlng.lat, lng: latlng.lng })
        });
    }

    function numero(valor, decimales) {
        return valor.toLocaleString('es-ES', { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
    }

    function grados(valor, positivo, negativo) {
        return numero(Math.abs(valor), 5) + '° ' + (valor >= 0 ? positivo : negativo);
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
            valor.className = 'badge bg-secondary rounded-pill';
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

    function celda(etiqueta, texto) {
        const elemento = document.createElement(etiqueta);
        elemento.textContent = texto;
        return elemento;
    }

    // Con cuántos datos se calculó una media, para el texto emergente de cada mes.
    function explicarMedia(m) {
        if (m.periodicidad === 'DIARIA') {
            return m.num_datos + (m.num_datos === 1 ? ' día muestreado' : ' días muestreados');
        }
        return numero(m.num_datos, 0) + ' horas válidas (' + Math.round(m.cobertura * 100) + ' % del mes)';
    }

    // Tabla con las doce medias mensuales del contaminante elegido.
    function pintarMeses() {
        const contaminante = detalleActual.contaminantes[ficha.contaminante.value];
        const porMes = {};
        (contaminante ? contaminante.mediciones : []).forEach(function (m) { porMes[m.mes] = m; });

        ficha.unidad.textContent = contaminante ? contaminante.nombre.toLowerCase() + ', en ' + contaminante.unidad.replace('m3', 'm³') : '';
        document.getElementById('fichaMesesCabecera').replaceChildren(...MESES.map(function (mes) { return celda('th', mes); }));
        document.getElementById('fichaMesesValores').replaceChildren(...MESES.map(function (_, i) {
            const m = porMes[i + 1];
            if (!m) return celda('td', '—');
            const td = celda('td', numero(m.media, 1) + (m.pocos_datos ? '*' : ''));
            td.title = explicarMedia(m);
            if (m.pocos_datos) td.className = 'pocos-datos';
            return td;
        }));
        ficha.notaPocosDatos.hidden = !Object.values(porMes).some(function (m) { return m.pocos_datos; });
    }

    function pintarDetalle(d) {
        detalleActual = d;
        // Municipio, provincia y comunidad, sin repetir nombres (Madrid, Madrid, Madrid) ni el de la estación.
        const lugar = [d.municipio, d.provincia, d.comunidad].filter(function (nombre, i, todos) {
            return nombre !== d.nombre && todos.indexOf(nombre) === i;
        });
        ficha.lugar.textContent = lugar.join(', ');
        document.getElementById('fichaTipo').textContent = d.tipo + ', área ' + d.area.toLowerCase();
        document.getElementById('fichaAltitud').textContent = numero(d.altitud, 0) + ' m';
        document.getElementById('fichaRed').textContent = d.red;
        document.getElementById('fichaDireccion').textContent = d.direccion || 'Sin dirección';

        const wgs84 = d.coordenadas.wgs84;
        const utm = d.coordenadas.utm;
        document.getElementById('fichaWgs84').textContent = grados(wgs84.lat, 'N', 'S') + ', ' + grados(wgs84.lng, 'E', 'O');
        document.getElementById('fichaUtmNombre').textContent =
            'UTM huso ' + utm.huso + ' (EPSG:' + utm.epsg + ')';
        document.getElementById('fichaUtm').textContent =
            'X ' + numero(utm.x, 2) + ' m, Y ' + numero(utm.y, 2) + ' m';

        // Selector de contaminantes: primero los que tienen datos; por defecto el NO2 si lo mide.
        const conDatos = d.contaminantes.filter(function (c) { return c.mediciones.length > 0; });
        ficha.contaminante.replaceChildren(...d.contaminantes.map(function (c, i) {
            const opcion = new Option(c.abreviatura, i);
            opcion.disabled = c.mediciones.length === 0;
            return opcion;
        }));
        const porDefecto = conDatos.find(function (c) { return c.abreviatura === 'NO2'; }) || conDatos[0];
        ficha.contaminante.value = d.contaminantes.indexOf(porDefecto);
        ficha.contaminante.disabled = conDatos.length === 0;
        ficha.sinMediciones.hidden = conDatos.length > 0;
        pintarMeses();
    }

    function cargarCercanas() {
        const id = fichaActual;
        const km = ficha.radio.value;
        rellenarLista(ficha.cercanas, [], 'Buscando…');

        pedirJson('/api/estaciones/' + id + '/cercanas/?km=' + km).then(function (datos) {
            // Si mientras tanto se abrió otra ficha o se cambió el radio, esta respuesta ya no vale.
            if (id !== fichaActual || km !== ficha.radio.value) return;
            rellenarLista(ficha.cercanas, datos.cercanas.map(function (c) {
                return elementoLista(c.nombre + ' (' + c.municipio + ')', numero(c.distancia_km, 1) + ' km');
            }), 'Ninguna estación en ese radio');
        }).catch(function (error) {
            console.error('No se pudieron cargar las estaciones cercanas:', error);
            rellenarLista(ficha.cercanas, [], 'No se pudieron cargar las estaciones cercanas. Prueba otra vez.');
        });
    }

    function mostrarFicha(propiedades) {
        const id = propiedades.id;
        fichaActual = id;
        ficha.nombre.textContent = propiedades.nombre;
        ficha.lugar.textContent = '';
        ficha.cargando.textContent = 'Cargando la estación…';
        ficha.cargando.hidden = false;
        ficha.contenido.hidden = true;
        modal.show();

        pedirJson('/api/estaciones/' + id + '/').then(function (detalle) {
            if (id !== fichaActual) return;
            pintarDetalle(detalle);
            ficha.cargando.hidden = true;
            ficha.contenido.hidden = false;
        }).catch(function (error) {
            console.error('No se pudo cargar la estación:', error);
            ficha.cargando.textContent = 'No se pudo cargar la estación. Cierra la ficha y vuelve a abrirla.';
        });
        cargarCercanas();
    }

    ficha.contaminante.addEventListener('change', pintarMeses);
    ficha.radio.addEventListener('change', cargarCercanas);

    function pintarEstaciones(datos) {
        const capaEstaciones = L.geoJSON(datos, {
            pointToLayer: function (feature, latlng) {
                return L.marker(latlng, {
                    icon: L.divIcon({ className: 'estacion estacion-' + feature.properties.tipo.toLowerCase(), iconSize: [14, 14] }),
                    title: feature.properties.nombre,
                    alt: 'Estación ' + feature.properties.nombre
                });
            },
            onEachFeature: function (feature, layer) {
                layer.on('click', function () {
                    // Al soltar un marcador arrastrado llega también un clic: no abre la ficha.
                    if (layer.pm && layer.pm.dragging()) return;
                    mostrarFicha(feature.properties);
                });

                // Fin del arrastre (modo "arrastrar" de Geoman): se guarda la posición corregida.
                layer.on('pm:dragend', function (evento) {
                    const marcador = evento.layer || layer;
                    guardarUbicacion(feature.properties.id, marcador.getLatLng()).catch(function (error) {
                        console.error('No se pudo guardar la ubicación:', error);
                        alert('No se pudo guardar la nueva ubicación (tiene que estar dentro de España). '
                            + 'Recarga la página para ver la posición guardada.');
                    });
                });
            }
        });

        // Las estaciones cercanas se agrupan en un círculo con su número.
        const grupos = L.markerClusterGroup({ maxClusterRadius: 50 });
        grupos.addLayer(capaEstaciones);
        mapa.addLayer(grupos);

        // En modo arrastrar se desagrupan para poder mover cada marcador;
        // al salir se vuelven a agrupar con las posiciones nuevas.
        mapa.on('pm:globaldragmodetoggled', function (evento) {
            if (evento.enabled) {
                mapa.removeLayer(grupos);
                capaEstaciones.addTo(mapa);
            } else {
                mapa.removeLayer(capaEstaciones);
                grupos.clearLayers();
                grupos.addLayer(capaEstaciones);
                mapa.addLayer(grupos);
            }
        });
    }

    pedirJson(elementoMapa.dataset.urlEstaciones).then(pintarEstaciones).catch(function (error) {
        console.error('No se pudieron cargar las estaciones:', error);
        alert('No se pudieron cargar las estaciones. Prueba a recargar la página.');
    });
});
