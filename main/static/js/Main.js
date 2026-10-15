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

    // Si la API responde con error, el Error lleva el estado y el mensaje que explica el servidor.
    function pedirJson(url, opciones) {
        return fetch(url, opciones).then(function (respuesta) {
            if (respuesta.ok) return respuesta.json();
            return respuesta.json().catch(function () { return {}; }).then(function (cuerpo) {
                const error = new Error('El servidor respondió ' + respuesta.status);
                error.estado = respuesta.status;
                error.mensaje = cuerpo.msg;
                throw error;
            });
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

    // Un decimal desde 1 y tres por debajo: los metales se miden en centésimas de ng/m³.
    function medida(valor) {
        return numero(valor, Math.abs(valor) >= 1 ? 1 : 3);
    }

    // Un límite legal se muestra con decimales solo si los tiene (40 µg/m³, pero 3,4 µg/m³).
    function valorLimite(valor) {
        return numero(valor, Number.isInteger(valor) ? 0 : 1);
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

    // ---- Gráfico de medias mensuales con la media anual y los límites legales anuales ----

    const SVG = 'http://www.w3.org/2000/svg';
    const COLOR_MES = '#2a78d6';
    const COLOR_MES_POCOS_DATOS = '#9ec5f4';
    const COLOR_MEDIA_ANUAL = '#104281';
    const COLOR_LIMITE = '#333333';

    function elementoSvg(etiqueta, atributos, padre) {
        const e = document.createElementNS(SVG, etiqueta);
        Object.keys(atributos).forEach(function (k) { e.setAttribute(k, atributos[k]); });
        if (padre) padre.appendChild(e);
        return e;
    }

    // Paso "redondo" para el eje: 1, 2, 2,5 o 5 por una potencia de 10.
    function pasoEje(maximo, marcas) {
        const bruto = maximo / marcas;
        const potencia = Math.pow(10, Math.floor(Math.log10(bruto)));
        const paso = [1, 2, 2.5, 5, 10].map(function (m) { return m * potencia; }).find(function (p) { return p >= bruto; });
        return paso;
    }

    // Barra con la parte superior redondeada (4 px) y la base recta.
    function rutaBarra(x, y, ancho, base) {
        const r = Math.min(4, ancho / 2, base - y);
        return 'M' + x + ',' + base + 'V' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
            'H' + (x + ancho - r) + 'Q' + (x + ancho) + ',' + y + ' ' + (x + ancho) + ',' + (y + r) + 'V' + base + 'Z';
    }

    // Líneas de referencia: la media anual y los límites (los de igual valor se dibujan una vez).
    function referencias(c) {
        const lineas = [];
        if (c.anual) {
            lineas.push({ valor: c.anual.media, texto: 'Media ' + c.anual.anno + ': ' + medida(c.anual.media), media: true });
        }
        c.limites.forEach(function (l) {
            if (lineas.some(function (r) { return !r.media && r.valor === l.valor; })) return;
            lineas.push({ valor: l.valor, texto: (l.desde >= 2030 ? 'Límite ' + l.desde : 'Límite actual') + ': ' + valorLimite(l.valor) });
        });
        return lineas;
    }

    function pintarGrafico(c) {
        const contenedor = document.getElementById('fichaGrafico');
        contenedor.replaceChildren();
        if (!c || c.mediciones.length === 0) return;

        const ancho = 640, alto = 220, izquierda = 44, derecha = 132, arriba = 10, abajo = 24;
        const base = alto - abajo, banda = (ancho - izquierda - derecha) / 12;
        const lineas = referencias(c);
        const maximo = Math.max.apply(null, c.mediciones.map(function (m) { return m.media; })
            .concat(lineas.map(function (l) { return l.valor; }))) * 1.1 || 1;
        const paso = pasoEje(maximo, 4);
        const tope = Math.ceil(maximo / paso) * paso;
        const y = function (v) { return base - (v / tope) * (base - arriba); };
        const unidad = c.unidad.replace('m3', 'm³');

        const svg = elementoSvg('svg', {
            viewBox: '0 0 ' + ancho + ' ' + alto, role: 'img',
            'aria-label': 'Medias mensuales de ' + c.abreviatura + ' en ' + unidad + ', con la media anual y los límites anuales'
        }, contenedor);

        // Rejilla y eje Y (líneas finas y continuas, en segundo plano)
        for (let v = 0; v <= tope + paso / 2; v += paso) {
            elementoSvg('line', { x1: izquierda, x2: ancho - derecha, y1: y(v), y2: y(v), class: 'rejilla' }, svg);
            elementoSvg('text', { x: izquierda - 6, y: y(v) + 4, class: 'eje', 'text-anchor': 'end' }, svg).textContent = numero(v, paso < 1 ? 1 : 0);
        }

        // Barras de los meses con su texto emergente
        const porMes = {};
        c.mediciones.forEach(function (m) { porMes[m.mes] = m; });
        MESES.forEach(function (nombre, i) {
            const centro = izquierda + banda * (i + 0.5);
            elementoSvg('text', { x: centro, y: alto - 6, class: 'eje', 'text-anchor': 'middle' }, svg).textContent = nombre;
            const m = porMes[i + 1];
            if (!m) return;
            const grosor = Math.min(24, banda * 0.6);
            const barra = elementoSvg('path', {
                d: rutaBarra(centro - grosor / 2, y(m.media), grosor, base),
                fill: m.pocos_datos ? COLOR_MES_POCOS_DATOS : COLOR_MES, class: 'barra'
            }, svg);
            elementoSvg('title', {}, barra).textContent = nombre + ': ' + medida(m.media) + ' ' + unidad + '. ' + explicarMedia(m);
        });

        // Líneas de referencia con su etiqueta a la derecha (separadas si quedan muy juntas)
        let ultimaEtiqueta = -Infinity;
        lineas.slice().sort(function (a, b) { return b.valor - a.valor; }).forEach(function (l) {
            elementoSvg('line', {
                x1: izquierda, x2: ancho - derecha + 6, y1: y(l.valor), y2: y(l.valor),
                stroke: l.media ? COLOR_MEDIA_ANUAL : COLOR_LIMITE, class: l.media ? 'linea-media' : 'linea-limite'
            }, svg);
            const yEtiqueta = Math.max(y(l.valor) + 4, ultimaEtiqueta + 13);
            ultimaEtiqueta = yEtiqueta;
            elementoSvg('text', { x: ancho - derecha + 10, y: yEtiqueta, class: 'etiqueta-linea' }, svg).textContent = l.texto;
        });
    }

    // Comparación de la media anual con cada límite, con icono y texto.
    function pintarVeredicto(c) {
        const lista = document.getElementById('fichaVeredicto');
        lista.replaceChildren();
        if (!c) return;
        const unidad = c.unidad.replace('m3', 'm³');
        const anual = c.anual;
        const nota = function (texto) {
            const li = document.createElement('li');
            li.className = 'text-muted small';
            li.textContent = texto;
            lista.appendChild(li);
        };

        if (c.limites.length === 0) {
            if (c.sin_limite_anual) nota(c.sin_limite_anual);
            return;
        }
        if (!anual) return;
        if (!anual.valida) {
            nota('No se compara con los límites: la media de ' + anual.anno + ' solo tiene el ' + Math.round(anual.cobertura * 100) +
                ' % de ' + (anual.orientativa ? 'los días (hace falta al menos el 14 %).' : 'las horas (hace falta al menos el 90 %).'));
            return;
        }
        c.limites.forEach(function (l) {
            const li = document.createElement('li');
            const icono = document.createElement('span');
            icono.className = 'icono ' + (l.supera ? 'supera' : 'cumple');
            icono.setAttribute('aria-hidden', 'true');
            icono.textContent = l.supera ? '✕' : '✓';
            li.appendChild(icono);
            li.appendChild(document.createTextNode(
                (l.supera ? 'Por encima del ' : 'Por debajo del ') + l.tipo + ' anual de ' + valorLimite(l.valor) + ' ' + unidad +
                (l.desde >= 2030 ? ', que se aplicará desde ' + l.desde : '') + ' (' + l.norma + ').'));
            lista.appendChild(li);
        });
        if (anual.orientativa) {
            nota('Media orientativa: sale de un captador manual que muestreó el ' + Math.round(anual.cobertura * 100) + ' % de los días.');
        }
        if (['PM10', 'PM2.5'].includes(c.abreviatura)) {
            nota('Es la media bruta: la evaluación oficial descuenta los aportes naturales, como el polvo del Sáhara.');
        }
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
            const td = celda('td', medida(m.media) + (m.pocos_datos ? '*' : ''));
            td.title = explicarMedia(m);
            if (m.pocos_datos) td.className = 'pocos-datos';
            return td;
        }));
        ficha.notaPocosDatos.hidden = !Object.values(porMes).some(function (m) { return m.pocos_datos; });
        pintarGrafico(contaminante);
        pintarVeredicto(contaminante);
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

        // Coordenadas lejos del municipio declarado: probablemente un error en los datos del MITECO.
        const aviso = document.getElementById('fichaAvisoMunicipio');
        const municipio = d.municipio_geo;
        aviso.hidden = !(municipio && municipio.posible_error);
        if (!aviso.hidden) {
            aviso.textContent = 'Sus coordenadas caen en ' + municipio.nombre + ', a ' +
                numero(municipio.distancia_al_declarado_km, 1) + ' km del municipio que indica el MITECO (' +
                d.municipio + '). Puede haber un error en la ubicación o en el municipio.';
        }

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

    // ---- Cobertura: municipios coloreados según su distancia a la estación activa más cercana ----

    // Tres tramos ordenados respecto al radio elegido: un solo tono, de claro a oscuro.
    const TRAMOS_COBERTURA = [
        { color: '#9ec5f4', texto: function (r) { return 'A menos de ' + r + ' km'; } },
        { color: '#2a78d6', texto: function (r) { return 'Entre ' + r + ' y ' + 2 * r + ' km'; } },
        { color: '#104281', texto: function (r) { return 'A más de ' + 2 * r + ' km'; } }
    ];
    const ZOOM_MINIMO_MUNICIPIOS = 9;  // con menos zoom la zona visible tiene miles de municipios
    const cobertura = { activa: false, radio: 10, capa: null, peticion: 0 };

    function tramo(distanciaKm) {
        if (distanciaKm === null || distanciaKm > 2 * cobertura.radio) return 2;
        return distanciaKm <= cobertura.radio ? 0 : 1;
    }

    const controlCobertura = L.control({ position: 'topright' });
    controlCobertura.onAdd = function () {
        const caja = L.DomUtil.create('div', 'panel-cobertura');
        caja.innerHTML =
            '<button type="button" class="btn btn-sm btn-light w-100" aria-pressed="false">Ver cobertura</button>' +
            '<div class="cuerpo" hidden>' +
            '  <label class="d-flex align-items-center gap-2 mb-2">Radio' +
            '    <select class="form-select form-select-sm w-auto">' +
            '      <option value="10" selected>10 km</option><option value="25">25 km</option><option value="50">50 km</option>' +
            '    </select></label>' +
            '  <p class="resumen mb-2">Calculando…</p>' +
            '  <ul class="tramos list-unstyled mb-2"></ul>' +
            '  <p class="aviso-zoom text-muted small mb-2" hidden>Acerca el zoom para ver los municipios.</p>' +
            '  <details><summary>Cobertura por provincia</summary>' +
            '    <table class="table table-sm mb-0"><thead><tr><th scope="col">Provincia</th>' +
            '    <th scope="col" class="text-end">Población cubierta</th></tr></thead><tbody></tbody></table>' +
            '  </details>' +
            '</div>';
        L.DomEvent.disableClickPropagation(caja);
        L.DomEvent.disableScrollPropagation(caja);
        return caja;
    };
    controlCobertura.addTo(mapa);

    const panel = controlCobertura.getContainer();
    const botonCobertura = panel.querySelector('button');
    const selectorCobertura = panel.querySelector('select');

    function pintarTramos() {
        panel.querySelector('.tramos').replaceChildren(...TRAMOS_COBERTURA.map(function (t) {
            const li = document.createElement('li');
            const muestra = document.createElement('span');
            muestra.className = 'muestra';
            muestra.style.background = t.color;
            li.appendChild(muestra);
            li.appendChild(document.createTextNode(t.texto(cobertura.radio) + ' de una estación'));
            return li;
        }));
    }

    function cargarResumen() {
        const radio = cobertura.radio;
        panel.querySelector('.resumen').textContent = 'Calculando…';
        pedirJson('/api/cobertura/?km=' + radio).then(function (datos) {
            if (radio !== cobertura.radio) return;
            panel.querySelector('.resumen').textContent =
                'El ' + numero(datos.poblacion.porcentaje, 1) + ' % de la población vive en un municipio con una estación ' +
                'a menos de ' + radio + ' km (' + numero(datos.municipios.cubiertos, 0) + ' de ' +
                numero(datos.municipios.total, 0) + ' municipios).';
            panel.querySelector('tbody').replaceChildren(...datos.provincias.map(function (p) {
                const fila = document.createElement('tr');
                fila.appendChild(celda('td', p.nombre));
                const valor = celda('td', numero(p.porcentaje, 1) + ' %');
                valor.className = 'text-end';
                fila.appendChild(valor);
                return fila;
            }));
        }).catch(function (error) {
            console.error('No se pudo calcular la cobertura:', error);
            panel.querySelector('.resumen').textContent = 'No se pudo calcular la cobertura. Prueba otra vez.';
        });
    }

    function quitarMunicipios() {
        if (cobertura.capa) {
            mapa.removeLayer(cobertura.capa);
            cobertura.capa = null;
        }
    }

    function avisarZoom(texto) {
        const aviso = panel.querySelector('.aviso-zoom');
        aviso.hidden = !texto;
        aviso.textContent = texto || '';
    }

    function cargarMunicipios() {
        if (!cobertura.activa) return;
        if (mapa.getZoom() < ZOOM_MINIMO_MUNICIPIOS) {
            avisarZoom('Acerca el zoom para ver los municipios.');
            quitarMunicipios();
            return;
        }
        avisarZoom(null);
        const peticion = ++cobertura.peticion;
        pedirJson('/api/municipios/?bbox=' + mapa.getBounds().toBBoxString()).then(function (datos) {
            // Solo vale la respuesta de la última petición (al mover el mapa se piden otras).
            if (peticion !== cobertura.peticion || !cobertura.activa) return;
            quitarMunicipios();
            cobertura.capa = L.geoJSON(datos, {
                pmIgnore: true,  // el modo arrastrar no debe mover los municipios
                attribution: '© EuroGeographics for the administrative boundaries',
                style: function (f) {
                    return { color: '#ffffff', weight: 0.6, fillColor: TRAMOS_COBERTURA[tramo(f.properties.distancia_km)].color, fillOpacity: 0.55 };
                },
                onEachFeature: function (f, capa) {
                    const p = f.properties;
                    const distancia = p.distancia_km === 0 ? 'tiene estación en su término'
                        : p.distancia_km === null ? 'sin estaciones activas'
                        : 'estación más cercana a ' + numero(p.distancia_km, 1) + ' km';
                    capa.bindTooltip(p.nombre + ': ' + numero(p.poblacion, 0) + ' hab., ' + distancia, { sticky: true });
                }
            }).addTo(mapa);
            cobertura.capa.bringToBack();
        }).catch(function (error) {
            if (peticion !== cobertura.peticion) return;
            quitarMunicipios();
            // 400: la zona tiene demasiados municipios; el servidor explica qué hacer.
            avisarZoom(error.estado === 400 && error.mensaje ? error.mensaje + '.'
                : 'No se pudieron cargar los municipios. Mueve el mapa para volver a intentarlo.');
            console.error('No se pudieron cargar los municipios:', error);
        });
    }

    botonCobertura.addEventListener('click', function () {
        cobertura.activa = !cobertura.activa;
        botonCobertura.setAttribute('aria-pressed', String(cobertura.activa));
        botonCobertura.textContent = cobertura.activa ? 'Ocultar cobertura' : 'Ver cobertura';
        panel.querySelector('.cuerpo').hidden = !cobertura.activa;
        if (cobertura.activa) {
            pintarTramos();
            cargarResumen();
            cargarMunicipios();
        } else {
            quitarMunicipios();
        }
    });

    selectorCobertura.addEventListener('change', function () {
        cobertura.radio = Number(selectorCobertura.value);
        pintarTramos();
        cargarResumen();
        if (cobertura.capa) {
            cobertura.capa.setStyle(function (f) {
                return { fillColor: TRAMOS_COBERTURA[tramo(f.properties.distancia_km)].color };
            });
        }
    });

    mapa.on('moveend', cargarMunicipios);

    pedirJson(elementoMapa.dataset.urlEstaciones).then(pintarEstaciones).catch(function (error) {
        console.error('No se pudieron cargar las estaciones:', error);
        alert('No se pudieron cargar las estaciones. Prueba a recargar la página.');
    });
});
