export function validationMessage(message: string): string {
  return message.replace(/^Value error,\s*/i, "");
}

export function lessonCount(count: number): string {
  const lastTwo = count % 100;
  const last = count % 10;
  const word = lastTwo >= 11 && lastTwo <= 14 ? "занятий"
    : last === 1 ? "занятие" : last >= 2 && last <= 4 ? "занятия" : "занятий";
  return `${count} ${word} на неделе`;
}
