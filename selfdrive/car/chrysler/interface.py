#!/usr/bin/env python3
from cereal import car
from panda import Panda
from openpilot.selfdrive.car import get_safety_config
from openpilot.selfdrive.car.chrysler.values import CAR, RAM_HD, RAM_DT, RAM_CARS, ChryslerFlags
from openpilot.selfdrive.car.interfaces import CarInterfaceBase


class CarInterface(CarInterfaceBase):
  @staticmethod
  def _get_params(ret, candidate, fingerprint, car_fw, experimental_long, docs):
    ret.carName = "chrysler"

    # radar parsing needs some work, see https://github.com/commaai/openpilot/issues/26842
    ret.radarUnavailable = True # DBC[candidate]['radar'] is None
    ret.steerActuatorDelay = 0.1
    ret.steerLimitTimer = 0.4
    ret.customStockLongAvailable = True

    # safety config
    ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.chrysler)]
    if candidate in RAM_HD:
      ret.safetyConfigs[0].safetyParam |= Panda.FLAG_CHRYSLER_RAM_HD
    elif candidate in RAM_DT:
      ret.safetyConfigs[0].safetyParam |= Panda.FLAG_CHRYSLER_RAM_DT

    ret.minSteerSpeed = 3.8  # m/s
    CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    if candidate not in RAM_CARS:
      # Newer FW versions standard on the following platforms, or flashed by a dealer onto older platforms have a higher minimum steering speed.
      new_eps_platform = candidate in (CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020, CAR.JEEP_GRAND_CHEROKEE_2019, CAR.DODGE_DURANGO)
      new_eps_firmware = any(fw.ecu == 'eps' and fw.fwVersion[:4] >= b"6841" for fw in car_fw)
      if new_eps_platform or new_eps_firmware:
        ret.flags |= ChryslerFlags.HIGHER_MIN_STEERING_SPEED.value

    # Chrysler
    if candidate in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020, CAR.DODGE_DURANGO):
      ret.mass = 2242.
      ret.wheelbase = 3.089
      ret.steerRatio = 16.2  # Pacifica Hybrid 2017

      ret.lateralTuning.init('pid')
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
      ret.lateralTuning.pid.kf = 0.00006

    # Jeep
    elif candidate in (CAR.JEEP_GRAND_CHEROKEE, CAR.JEEP_GRAND_CHEROKEE_2019):
      ret.mass = 1778
      ret.wheelbase = 2.71
      ret.steerRatio = 16.7
      ret.steerActuatorDelay = 0.2

      ret.lateralTuning.init('pid')
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
      ret.lateralTuning.pid.kf = 0.00006

    # Ram
    elif candidate == CAR.RAM_1500:
      ret.steerActuatorDelay = 0.2
      ret.wheelbase = 3.88
      ret.steerRatio = 16.3
      ret.mass = 2493.
      ret.minSteerSpeed = 0.5
      ret.minEnableSpeed = 14.5
      if any(fw.ecu == 'eps' and fw.fwVersion in (b"68273275AF", b"68273275AG", b"68312176AE", b"68312176AG",) for fw in car_fw):
        ret.minEnableSpeed = 0.

    elif candidate == CAR.RAM_HD:
      ret.steerActuatorDelay = 0.2
      ret.wheelbase = 3.785
      ret.steerRatio = 15.61
      ret.mass = 3405.
      ret.minSteerSpeed = 16
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning, 1.0, False)

    else:
      raise ValueError(f"Unsupported car: {candidate}")

    if ret.flags & ChryslerFlags.HIGHER_MIN_STEERING_SPEED:
      # TODO: allow these cars to steer down to 13 m/s if already engaged.
      # TODO: Durango 2020 may be able to steer to zero once above 38 kph
      ret.minSteerSpeed = 17.5  # m/s 17 on the way up, 13 on the way down once engaged.

    ret.centerToFront = ret.wheelbase * 0.44
    ret.enableBsm = 720 in fingerprint[0]

    return ret

  def _update(self, c):
    ret = self.CS.update(self.cp, self.cp_cam)

    # events
    events = self.create_common_events(ret, extra_gears=[car.CarState.GearShifter.low])

    # Low speed steer alert hysteresis logic
    if self.CP.carFingerprint in RAM_DT:
      if self.CS.out.vEgo >= self.CP.minEnableSpeed:
        self.low_speed_alert = False
      if (self.CP.minEnableSpeed >= 14.5) and (self.CS.out.gearShifter != car.CarState.GearShifter.drive):
        self.low_speed_alert = True
    else:
      if self.CP.minSteerSpeed > 0. and ret.vEgo < (self.CP.minSteerSpeed + 0.5):
        self.low_speed_alert = True
      elif ret.vEgo > (self.CP.minSteerSpeed + 1.):
        self.low_speed_alert = False
    if self.low_speed_alert:
      events.add(car.CarEvent.EventName.belowSteerSpeed)

    ret.events = events.to_msg()

    return ret

  def apply(self, c, now_nanos):
    return self.CC.update(c, self.CS, now_nanos)
