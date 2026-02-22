export const awsConfig = {
  Auth: {
    Cognito: {
      userPoolId: 'us-west-2_ShLZKKlgJ',
      userPoolClientId: '4s4jasj56nh147iujbj45m8100',
      loginWith: {
        oauth: {
          domain: 'menu-vision-app.auth.us-west-2.amazoncognito.com',
          scopes: ['openid', 'email', 'profile'],
          redirectSignIn: ['https://d2cc8vlucyqtpu.cloudfront.net/'],
          redirectSignOut: ['https://d2cc8vlucyqtpu.cloudfront.net/'],
          responseType: 'code' as const,
        },
      },
    },
  },
};

export const API_BASE_URL = 'https://6s86xcu7ia.execute-api.us-west-2.amazonaws.com/prod';
