# Configuración de GEMINI.md para Máximo Control

El archivo `GEMINI.md` contiene mandatos de "Seguridad Blanda" que el modelo carga en su sistema de prompts primario.


| Regla Global         | Descripción Técnica                                                                                                       | Justificación                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Permission-First** | "Nunca ejecutes comandos de terminal que hagan modificaciones o crees archivos sin aprobación explícita (PLAN APPROVED)." | Evita cambios destructivos automatizados.                     |
| **No assumptions**   | "Si la petición es ambigua o faltan requisitos técnicos, es obligatorio preguntar al usuario."                            | Reduce el desperdicio de tokens por retrabajo.                |
| **Context Hygiene**  | "Si el contexto se vuelve confuso, sugiere iniciar una nueva conversación."                                               | Previene alucinaciones por sobrecarga de ventana de contexto. |
| **Scope Lock**       | "Prohibido modificar código fuera de la zona activa definida por el cursor o la petición."                                | Mantiene la integridad de las secciones estables del repo.    |
