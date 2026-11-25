const dialogoFundo = document.querySelector("#asignar-fundo");
if (dialogoFundo) {
  const botonAsignar = document.querySelector("[data-asignar-fundo]");
  botonAsignar.addEventListener("click", () => dialogoFundo.showModal());
  dialogoFundo.querySelector("[data-cancelar-fundo]").addEventListener("click", () => dialogoFundo.close());
  if (dialogoFundo.hasAttribute("data-reabrir")) dialogoFundo.showModal();
}
