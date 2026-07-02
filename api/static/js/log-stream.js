function iniciarStreamLog(execucaoId, elementoId) {
  const pre = document.getElementById(elementoId);
  const es = new EventSource(`/execucoes/${execucaoId}/stream`);

  es.onmessage = (evt) => {
    pre.textContent += evt.data + "\n";
    pre.scrollTop = pre.scrollHeight;
  };

  es.addEventListener("fim", () => {
    es.close();
    window.location.reload();
  });

  es.onerror = () => {
    es.close();
  };
}
