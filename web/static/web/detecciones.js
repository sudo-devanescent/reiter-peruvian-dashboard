const moduloDetecciones = document.querySelector("[data-modulo]");
if (moduloDetecciones) {
  const formulario = moduloDetecciones.form;
  const caseta = formulario.querySelector("[data-caseta]");
  moduloDetecciones.addEventListener("change", () => {
    caseta.value = "";
    formulario.requestSubmit();
  });
  caseta.addEventListener("change", () => formulario.requestSubmit());
}
