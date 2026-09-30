import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listarAlertas, reconocerAlerta } from '../services/catalogApi'

export const useAlertas = (habilitado: boolean) =>
  useQuery({
    queryKey: ['alertas'],
    queryFn: listarAlertas,
    enabled: habilitado,
    refetchInterval: 60_000,
  })

export function useReconocerAlerta() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => reconocerAlerta(id),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ['alertas'] }),
    // Otra sesión pudo reconocerla antes (409/404): se recarga la bandeja para reflejarlo.
    onError: () => cliente.invalidateQueries({ queryKey: ['alertas'] }),
  })
}
