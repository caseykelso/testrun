/*
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { createAction, props } from '@ngrx/store';
import {
  InterfacesValidation,
  SettingMissedError,
  SystemConfig,
} from '../model/setting';
import { SystemInterfaces } from '../model/setting';
import { Device } from '../model/device';
import { TestrunStatus } from '../model/testrun-status';
import { Profile } from '../model/profile';

// App component
export const toggleMenu = createAction('[App Component] Toggle Menu');

export const fetchInterfaces = createAction('[App Component] Fetch Interfaces');

export const fetchInterfacesSuccess = createAction(
  '[App Component] Fetch interfaces Success',
  props<{ interfaces: SystemInterfaces }>()
);

export const updateFocusNavigation = createAction(
  '[App Component] update focus navigation',
  props<{ focusNavigation: boolean }>()
);

export const updateValidInterfaces = createAction(
  '[App Component] Update Valid Interfaces',
  props<{ validInterfaces: InterfacesValidation }>()
);

export const updateError = createAction(
  '[App Component] Update Setting Missed Error',
  props<{ settingMissedError: SettingMissedError }>()
);

// Settings
export const fetchSystemConfigSuccess = createAction(
  '[Settings] Fetch System Config Success',
  props<{ systemConfig: SystemConfig }>()
);

// Shared
export const setHasConnectionSettings = createAction(
  '[Shared] Set Has Connection Settings',
  props<{ hasConnectionSettings: boolean }>()
);

export const setIsOpenAddDevice = createAction(
  '[Shared] Set Is Open Add Device',
  props<{ isOpenAddDevice: boolean }>()
);

export const setIsStopTestrun = createAction('[Shared] Set Is Stop Testrun');

export const setIsOpenWaitSnackBar = createAction(
  '[Shared] Set Is Open WaitSnackBar',
  props<{ isOpenWaitSnackBar: boolean }>()
);

export const setHasDevices = createAction(
  '[Shared] Set Has Devices',
  props<{ hasDevices: boolean }>()
);

export const setDevices = createAction(
  '[Shared] Set Devices',
  props<{ devices: Device[] }>()
);

export const setHasRiskProfiles = createAction(
  '[Shared] Set Has Risk Profiles',
  props<{ hasRiskProfiles: boolean }>()
);

export const setRiskProfiles = createAction(
  '[Shared] Set Risk Profiles',
  props<{ riskProfiles: Profile[] }>()
);

export const setTestrunStatus = createAction(
  '[Shared] Set Testrun Status',
  props<{ systemStatus: TestrunStatus }>()
);

export const setIsOpenStartTestrun = createAction(
  '[Shared] Set Is Open Start Testrun',
  props<{ isOpenStartTestrun: boolean }>()
);

export const setDeviceInProgress = createAction(
  '[Shared] Set Device In Progress',
  props<{ device: Device | null }>()
);

export const fetchSystemStatus = createAction('[Shared] Fetch system status');

export const fetchSystemStatusSuccess = createAction(
  '[Shared] Fetch system status success',
  props<{ systemStatus: TestrunStatus }>()
);

export const setStatus = createAction(
  '[Shared] Set Status',
  props<{ status: string }>()
);

export const stopInterval = createAction('[Shared] Stop Interval');

export const fetchRiskProfiles = createAction('[Shared] Fetch risk profiles');
