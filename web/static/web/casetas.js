const dialogoCaseta = document.querySelector("#form-caseta");
if (dialogoCaseta) {
  const botonAgregar = document.querySelector("[data-agregar-caseta]");
  const botonCancelar = dialogoCaseta.querySelector("[data-cancelar-caseta]");
  const abrir = () => {
    if (!dialogoCaseta.open) dialogoCaseta.showModal();
  };

  botonAgregar.addEventListener("click", (evento) => {
    if (dialogoCaseta.hasAttribute("data-restablecer")) return;
    evento.preventDefault();
    abrir();
  });

  botonCancelar.addEventListener("click", (evento) => {
    if (dialogoCaseta.hasAttribute("data-restablecer")) return;
    evento.preventDefault();
    dialogoCaseta.close();
  });

  dialogoCaseta.addEventListener("cancel", (evento) => {
    if (!dialogoCaseta.hasAttribute("data-restablecer")) return;
    evento.preventDefault();
    window.location.assign(botonCancelar.href);
  });

  if (dialogoCaseta.hasAttribute("data-abrir") || window.location.hash === "#form-caseta") {
    abrir();
  }
}

const dialogoModulo = document.querySelector("#form-modulo");
if (dialogoModulo) {
  const formulario = dialogoModulo.querySelector("form");
  const titulo = dialogoModulo.querySelector("h2");
  const cancelar = dialogoModulo.querySelector("[data-cancelar-modulo]");

  if (dialogoModulo.hasAttribute("data-abrir-modulo")) {
    dialogoModulo.showModal();
    dialogoModulo.addEventListener("cancel", (evento) => {
      evento.preventDefault();
      window.location.assign(cancelar.href);
    });
  } else {
    document.querySelectorAll("[data-abrir-formulario-modulo]").forEach((enlace) => {
      enlace.addEventListener("click", (evento) => {
        if (evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
        evento.preventDefault();
        formulario.action = enlace.href;
        formulario.elements.namedItem("nombre").value = enlace.dataset.nombreModulo || "";
        formulario.elements.namedItem("fundo").value = enlace.dataset.fundoModulo || "";
        titulo.textContent = enlace.dataset.tituloModulo;
        dialogoModulo.showModal();
      });
    });

    cancelar.addEventListener("click", (evento) => {
      evento.preventDefault();
      dialogoModulo.close();
    });
  }
}
