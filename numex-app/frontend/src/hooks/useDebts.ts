import { useQuery } from '@tanstack/react-query'
import { getDebts } from '../services/api'
import { mapDebtToCardData, type DebtCardData } from '../types/debt'

export function useDebts() {
  return useQuery({
    queryKey: ['debts'],
    queryFn: getDebts,
  })
}

export function useDebtCards() {
  const { data: debts, ...rest } = useDebts()
  
  const cards: DebtCardData[] = debts?.map(mapDebtToCardData) ?? []
  
  return {
    data: cards,
    ...rest,
  }
}
