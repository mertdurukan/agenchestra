// Orkestra'nın tek hooks modülü: eklenti tek modül kabul eder, bu yüzden parçalar burada birleşir.
import type { Register } from 'claude-code'

import { register as arkaPlanSeridi } from './arka_plan_seridi'
import { register as sayac } from './sayac'

export const register: Register = (on, options) => {
  sayac(on, options)
  arkaPlanSeridi(on, options)
}
